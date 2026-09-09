# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_finapi import sca as sca_flow
from erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings import get_client
from erpnext_finapi.session import get_user_session


class finAPIUser(Document):
	pass


@frappe.whitelist()
def register(user: str):
	"""Register this user at finAPI (``POST /api/v2/users``, data client).

	Stores the returned finAPI user id and, if finAPI generated a password,
	persists it. Idempotent-ish: re-running on an already-registered user will
	attempt creation again, which finAPI rejects — guard in the UI.
	"""
	doc = frappe.get_doc("finAPI User", user)
	# Before the finAPI call, not after: doc.save() below would catch an unauthorized
	# caller, but only once the user already exists at finAPI. finAPI rejects a second
	# creation, so that would leave this record permanently unregisterable.
	doc.check_permission("write")

	# The user's own environment, not a global one: Sandbox and Live are separate pools,
	# and finAPI Settings carries the credentials for both.
	client = get_client(doc.environment)
	result = client.create_user(
		user_id=doc.finapi_username or None,
		password=doc.get_password("finapi_password") if doc.finapi_password else None,
	)
	doc.finapi_user_id = result.get("id") or doc.finapi_username
	if result.get("password") and not doc.finapi_password:
		doc.finapi_password = result["password"]
	doc.is_registered = 1
	doc.save()
	return {"ok": True, "user_id": doc.finapi_user_id}


@frappe.whitelist()
def discover_connections(user: str) -> dict:
	"""Adopt the bank connections this finAPI user already has.

	A finAPI user often predates its ERPNext record — it was created by a previous
	system, or the connection was imported through finAPI's own web form. Rather than
	forcing a fresh SCA import (and a second consent), this pulls what already exists
	and creates the matching ``finAPI Bank Connection`` records, accounts included.
	"""
	doc = frappe.get_doc("finAPI User", user)
	doc.check_permission("write")

	client, token = get_user_session(user)
	connections = client.get_bank_connections(token=token)

	created, updated = [], []
	for payload in connections:
		connection_id = str(payload.get("id"))
		bank = payload.get("bank") or {}

		name = frappe.db.get_value("finAPI Bank Connection", {"finapi_connection_id": connection_id})
		if name:
			connection = frappe.get_doc("finAPI Bank Connection", name)
			updated.append(name)
		else:
			connection = frappe.new_doc("finAPI Bank Connection")
			connection.finapi_user = user
			connection.finapi_connection_id = connection_id
			connection.connection_name = bank.get("name") or _("finAPI connection {0}").format(connection_id)
			created.append(connection_id)

		connection.bank_name = bank.get("name") or connection.bank_name
		connection.finapi_bank_id = str(bank.get("id")) if bank.get("id") else connection.finapi_bank_id
		connection.interface = _first_interface(payload) or connection.interface
		connection.status = "Connected"
		connection.consent_expiry = sca_flow.consent_expiry(payload)
		connection.bank = _match_erpnext_bank(bank)

		sca_flow.map_accounts(connection, client=client, token=token)
		connection.save()

	return {
		"connections": len(connections),
		"created": created,
		"updated": updated,
	}


def _first_interface(payload: dict) -> str | None:
	for interface in payload.get("interfaces") or []:
		if isinstance(interface, dict) and interface.get("bankingInterface"):
			return interface["bankingInterface"]
	return None


def _match_erpnext_bank(bank: dict) -> str | None:
	"""Link a native ``Bank`` by name — never create one, that is the user's call."""
	name = bank.get("name")
	if not name:
		return None
	return frappe.db.exists("Bank", name) or frappe.db.get_value("Bank", {"bank_name": name})

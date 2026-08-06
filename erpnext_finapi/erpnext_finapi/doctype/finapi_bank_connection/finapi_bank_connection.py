# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_finapi import sca as sca_flow
from erpnext_finapi import sync as sync_engine
from erpnext_finapi.finapi import constants as c
from erpnext_finapi.session import get_user_session


class finAPIBankConnection(Document):
	"""A bank connection imported from finAPI.

	The SCA flows live in :mod:`erpnext_finapi.sca`, the transaction sync in
	:mod:`erpnext_finapi.sync`. This controller only exposes them to the Desk.
	"""

	def on_update(self):
		# Accounts usually get linked by hand the first time: an ERPNext Bank Account
		# frequently has no IBAN stored, so the automatic IBAN match finds nothing.
		# Close that loop here — write back what the bank told us, so the mapping is a
		# one-off and every later account matches by itself.
		for row in self.accounts or []:
			if not (row.bank_account and row.finapi_account_id):
				continue
			sca_flow.stamp_integration_id(row.bank_account, str(row.finapi_account_id), row.iban)
			sca_flow.backfill_iban(row.bank_account, row.iban)

	def on_trash(self):
		# Never leave in-flight login credentials behind in the cache.
		sca_flow.clear_session(self.name)


def _load_credentials(login_credentials) -> list[dict]:
	"""Accept the dialog's JSON payload as well as an already-parsed list."""
	if isinstance(login_credentials, str):
		login_credentials = json.loads(login_credentials)
	return login_credentials or []


# --------------------------------------------------------------------------- #
# Bank search (needs a user token — a client token returns 403)
# --------------------------------------------------------------------------- #


def _check_setup_permission() -> None:
	"""Guard the setup helpers, which run before a connection document exists."""
	if not frappe.has_permission("finAPI Bank Connection", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def search_banks(search: str, finapi_user: str) -> list[dict]:
	"""Search finAPI's bank directory for the picker.

	Takes the finAPI User rather than a connection, so the search works while the
	connection is still an unsaved draft — that is exactly when you need it, since the
	bank id it returns is what you fill in.
	"""
	_check_setup_permission()

	settings = frappe.get_single("finAPI Settings")
	client, token = get_user_session(finapi_user)

	# finAPI's fake banks are what you want in Sandbox and pure noise in Live.
	banks = (
		client.search_banks(
			search,
			token=token,
			is_test_bank=(settings.environment == c.SANDBOX),
		).get("banks")
		or []
	)

	return [
		{
			"id": bank.get("id"),
			"name": bank.get("name"),
			"blz": bank.get("blz"),
			"bic": bank.get("bic"),
			"interfaces": [i.get("bankingInterface") for i in (bank.get("interfaces") or [])],
		}
		for bank in banks
	]


@frappe.whitelist()
def get_login_fields(finapi_user: str, bank_id: str, interface: str | None = None) -> list[dict]:
	"""The credential labels the chosen bank declares for the chosen interface.

	Banks differ (Anmeldename/PIN, Kundennummer/Passwort, …), so the dialog has to be
	built from what finAPI reports rather than from a hardcoded form.
	"""
	_check_setup_permission()

	if not bank_id:
		frappe.throw(_("Set the finAPI Bank ID first (use the bank search)."))

	client, token = get_user_session(finapi_user)
	bank = client.get_bank(bank_id, token=token)

	wanted = interface or c.INTERFACE_XS2A
	interfaces = bank.get("interfaces") or []
	interface = next((i for i in interfaces if i.get("bankingInterface") == wanted), None) or (
		interfaces[0] if interfaces else {}
	)

	# Some interfaces (pure redirect flows) declare no fields at all — that is valid.
	return [
		{"label": field.get("label"), "masked": bool(field.get("masked"))}
		for field in (interface.get("loginCredentials") or [])
	]


# --------------------------------------------------------------------------- #
# SCA flows
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def start_import(connection: str, login_credentials=None) -> dict:
	return sca_flow.start(connection, _load_credentials(login_credentials), mode="import")


@frappe.whitelist()
def start_update(connection: str, login_credentials=None) -> dict:
	"""Re-authorise an existing connection (the 90-day PSD2 re-consent)."""
	return sca_flow.start(connection, _load_credentials(login_credentials), mode="update")


@frappe.whitelist()
def submit_sca_step(connection: str, two_step_procedure_id=None, challenge_response=None) -> dict:
	return sca_flow.submit_step(
		connection,
		two_step_procedure_id=two_step_procedure_id,
		challenge_response=challenge_response,
	)


@frappe.whitelist()
def cancel_sca(connection: str) -> dict:
	return sca_flow.cancel(connection)


# --------------------------------------------------------------------------- #
# Accounts & sync
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def refresh_accounts(connection: str, include_removed: int = 0) -> dict:
	"""Re-read the accounts of this connection and re-try the Bank Account linking.

	Accounts you deleted from the table stay deleted — pass ``include_removed`` to pull
	them back in.
	"""
	doc = frappe.get_doc("finAPI Bank Connection", connection)
	doc.check_permission("write")

	if not doc.finapi_connection_id:
		frappe.throw(_("This connection has not been imported yet."))

	client, token = get_user_session(doc.finapi_user)
	linked = sca_flow.map_accounts(
		doc, client=client, token=token, include_removed=bool(int(include_removed))
	)
	doc.save()

	return {"accounts": len(doc.accounts or []), "bank_accounts_linked": linked}


@frappe.whitelist()
def sync_now(connection: str, update_bank: int = 1) -> str:
	"""Queue a sync. Stage one plus its settle wait is far too slow for a web request."""
	doc = frappe.get_doc("finAPI Bank Connection", connection)
	doc.check_permission("write")

	frappe.enqueue(
		"erpnext_finapi.sync.sync_connection",
		queue="long",
		timeout=1500,
		connection=connection,
		update_bank=bool(int(update_bank)),
	)
	return _("Sync queued — the result appears as a finAPI Sync Log when it finishes.")


@frappe.whitelist()
def sync_now_foreground(connection: str, update_bank: int = 1) -> dict:
	"""Synchronous variant for the console and tests (bypasses the worker)."""
	frappe.get_doc("finAPI Bank Connection", connection).check_permission("write")
	return sync_engine.sync_connection(connection, update_bank=bool(int(update_bank)))

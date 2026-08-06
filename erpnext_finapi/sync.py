# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Transaction sync: finAPI ──▶ native ``Bank Transaction``.

**Every sync has two stages, and skipping the first one is the classic failure mode:**

	Stage 1  update_bank_connection()   finAPI ◀── bank   (fetch fresh data)
	Stage 2  get_transactions()         us     ◀── finAPI (read what finAPI holds)

Stage 2 alone never fails loudly — it just keeps returning the same snapshot taken at
import time, so the sync reports "nothing new" forever while the account fills up. The
predecessor system lost months to exactly this.

Everything downstream of ``Bank Transaction`` (matching, Payment Entries, clearing) is
native ERPNext and deliberately not reimplemented here.
"""

from __future__ import annotations

import time

import frappe
from frappe import _
from frappe.utils import add_days, getdate, now_datetime, today

from erpnext_finapi.finapi import constants as c
from erpnext_finapi.finapi.exceptions import FinApiError, ScaChallengeRequired
from erpnext_finapi.finapi.mapping import map_transaction, transaction_id
from erpnext_finapi.session import get_user_session

# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #


def sync_all_connections(update_bank: bool = True) -> list[dict]:
	"""Sync every enabled connection. Used by the scheduler."""
	settings = frappe.get_single("finAPI Settings")
	if not settings.auto_sync:
		return []

	connections = frappe.get_all(
		"finAPI Bank Connection",
		filters={"sync_enabled": 1, "status": ["in", ["Connected", "Update Required"]]},
		pluck="name",
	)

	results = []
	for connection in connections:
		# One broken connection must not stop the others.
		try:
			results.append(sync_connection(connection, update_bank=update_bank))
		except Exception:
			frappe.log_error(
				title=_("finAPI sync failed for {0}").format(connection),
				message=frappe.get_traceback(),
			)
	return results


def sync_connection(connection: str, *, update_bank: bool = True) -> dict:
	"""Run both stages for one connection and write a ``finAPI Sync Log``."""
	doc = frappe.get_doc("finAPI Bank Connection", connection)
	settings = frappe.get_single("finAPI Settings")

	log = frappe.new_doc("finAPI Sync Log")
	log.bank_connection = doc.name
	log.sync_start = now_datetime()

	try:
		client, token = get_user_session(doc.finapi_user)

		updated = False
		if update_bank and doc.finapi_connection_id:
			updated = _update_bank_connection(doc, client=client, token=token)

		if updated:
			# finAPI stores freshly fetched transactions slightly asynchronously; reading
			# immediately would miss them until the next run.
			time.sleep(c.POST_UPDATE_SETTLE_SECONDS)

		fetched, created = _import_transactions(doc, settings, client=client, token=token)

		doc.db_set("last_sync", now_datetime(), update_modified=False)
		if not doc.last_error:
			doc.db_set("last_error", None, update_modified=False)

		log.status = "Partial" if doc.status == "Update Required" else "Success"
		log.transactions_fetched = fetched
		log.transactions_created = created
		log.error_message = doc.last_error
	except Exception as e:
		log.status = "Error"
		log.error_message = str(e)[:1000]
		doc.db_set("status", "Error", update_modified=False)
		doc.db_set("last_error", str(e)[:1000], update_modified=False)
		frappe.log_error(
			title=_("finAPI sync failed for {0}").format(connection), message=frappe.get_traceback()
		)
	finally:
		log.sync_end = now_datetime()
		log.insert(ignore_permissions=True)

	return {
		"connection": doc.name,
		"status": log.status,
		"fetched": log.transactions_fetched or 0,
		"created": log.transactions_created or 0,
		"error": log.error_message,
	}


# --------------------------------------------------------------------------- #
# Stage 1 — make finAPI fetch from the bank
# --------------------------------------------------------------------------- #


def _update_bank_connection(doc, *, client, token: str) -> bool:
	"""Trigger an unattended update. Returns whether fresh data was fetched.

	Inside the 90-day consent window finAPI replays the stored secrets and no human is
	needed. If the bank insists on SCA there is nothing a scheduler can do — we flag the
	connection for a manual update and still read whatever finAPI already has.
	"""
	try:
		client.update_bank_connection(
			token=token,
			bank_connection_id=doc.finapi_connection_id,
			interface=doc.interface or c.INTERFACE_XS2A,
		)
		if doc.status != "Connected":
			doc.db_set("status", "Connected", update_modified=False)
		doc.db_set("last_error", None, update_modified=False)
		return True
	except ScaChallengeRequired:
		doc.db_set("status", "Update Required", update_modified=False)
		doc.db_set(
			"last_error",
			_("The bank requires strong authentication (TAN). Run 'Update connection' manually."),
			update_modified=False,
		)
		return False
	except FinApiError as e:
		# Reading can still succeed — record the reason, do not abort the sync.
		doc.db_set("last_error", str(e)[:1000], update_modified=False)
		return False


# --------------------------------------------------------------------------- #
# Stage 2 — read finAPI and write native Bank Transactions
# --------------------------------------------------------------------------- #


def _import_transactions(doc, settings, *, client, token: str) -> tuple[int, int]:
	accounts = {
		str(row.finapi_account_id): row.bank_account for row in (doc.accounts or []) if row.bank_account
	}
	if not accounts:
		doc.db_set(
			"last_error",
			_("No finAPI account is linked to an ERPNext Bank Account — nothing to import."),
			update_modified=False,
		)
		return 0, 0

	transactions = client.get_transactions(
		token=token,
		account_ids=[int(a) for a in accounts if str(a).isdigit()],
		min_import_date=_sync_since(doc, settings),
	)

	created = 0
	for transaction in transactions:
		bank_account = accounts.get(str(transaction.get("accountId")))
		if not bank_account:
			continue
		if create_bank_transaction(transaction, bank_account):
			created += 1

	_stamp_last_integration_date(accounts.values())
	return len(transactions), created


def _sync_since(doc, settings) -> str:
	"""The ``minImportDate`` cursor.

	Filtering on finAPI's *import* date is what makes this incremental: a transaction the
	bank booked days ago but only delivered today is still picked up. The overlap re-reads
	a little on purpose — duplicates cost nothing, gaps are silent.
	"""
	if doc.last_sync:
		overlap = int(settings.sync_overlap_days or 2)
		return str(getdate(add_days(doc.last_sync, -overlap)))

	initial = int(settings.initial_sync_days or 90)
	return str(getdate(add_days(today(), -initial)))


def create_bank_transaction(transaction: dict, bank_account: str) -> str | None:
	"""Create and submit one native ``Bank Transaction``. Returns its name, or None if known.

	Deduplication is by ``transaction_id`` so re-reading an overlapping window — or a
	retry after a half-finished run — never doubles anything.
	"""
	external_id = transaction_id(transaction.get("id"))
	if frappe.db.exists("Bank Transaction", {"transaction_id": external_id}):
		return None

	doc = frappe.get_doc(map_transaction(transaction, bank_account))
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _stamp_last_integration_date(bank_accounts) -> None:
	"""Keep the native ``last_integration_date`` current, like ERPNext's own feeds do."""
	for bank_account in set(bank_accounts):
		frappe.db.set_value("Bank Account", bank_account, "last_integration_date", today())


# --------------------------------------------------------------------------- #
# PSD2 consent watchdog
# --------------------------------------------------------------------------- #


def check_consent_expiry() -> list[str]:
	"""Warn before a 90-day consent lapses — an expired consent kills the sync silently."""
	settings = frappe.get_single("finAPI Settings")
	warning_days = int(settings.consent_warning_days or 14)
	deadline = add_days(now_datetime(), warning_days)

	connections = frappe.get_all(
		"finAPI Bank Connection",
		filters={
			"sync_enabled": 1,
			"status": ["in", ["Connected", "Update Required"]],
			"consent_expiry": ["<=", deadline],
		},
		fields=["name", "connection_name", "consent_expiry"],
	)

	for connection in connections:
		expired = getdate(connection.consent_expiry) <= getdate(today())
		if expired:
			frappe.db.set_value("finAPI Bank Connection", connection.name, "status", "Update Required")

		_notify_accountants(
			subject=(
				_("finAPI: consent for {0} has expired").format(connection.connection_name)
				if expired
				else _("finAPI: consent for {0} expires on {1}").format(
					connection.connection_name, connection.consent_expiry
				)
			),
			message=_(
				"PSD2 requires renewed strong authentication every 90 days. "
				"Open the bank connection and run 'Update connection' — without it the "
				"transaction sync stops delivering new transactions."
			),
			document_name=connection.name,
		)

	return [connection.name for connection in connections]


def _notify_accountants(*, subject: str, message: str, document_name: str) -> None:
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", ["Accounts Manager", "System Manager"]], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)

	for user in set(users):
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"subject": subject,
				"email_content": message,
				"for_user": user,
				"type": "Alert",
				"document_type": "finAPI Bank Connection",
				"document_name": document_name,
			}
		).insert(ignore_permissions=True)

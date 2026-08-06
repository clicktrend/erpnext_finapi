# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""The direct multi-step SCA flow (chipTAN & friends) as a server-side state machine.

finAPI answers ``POST /bankConnections/import`` (and ``/update``) with HTTP **510**
until Strong Customer Authentication is complete:

	login credentials ─▶ 510 TWO_STEP_PROCEDURE_REQUIRED  (pick a TAN scheme)
	                  ─▶ 510 CHALLENGE_RESPONSE_REQUIRED  (enter the TAN)
	                  ─▶ 201 bank connection created

Every step must re-send the **full** request body, so the in-flight login credentials
have to survive between browser round-trips. They are therefore held **server-side
only**, in the Frappe cache, under a short TTL, and are deleted the moment the flow
finishes or is cancelled. They are never returned to the client and never persisted
to the database (PSD2-sensitive).
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, now_datetime

from erpnext_finapi.finapi import constants as c
from erpnext_finapi.finapi.exceptions import ScaChallengeRequired
from erpnext_finapi.session import get_user_session

# How long an unfinished SCA flow may sit in the cache. TANs expire quickly anyway.
SESSION_TTL_SECONDS = 15 * 60

# PSD2 consent lifetime when finAPI does not tell us an explicit expiry.
DEFAULT_CONSENT_DAYS = 90


def _cache_key(connection: str) -> str:
	return f"erpnext_finapi:sca:{connection}"


def _load_session(connection: str) -> dict:
	session = frappe.cache().get_value(_cache_key(connection))
	if not session:
		frappe.throw(_("The authentication session has expired. Please start the import again."))
	return session


def _store_session(connection: str, session: dict) -> None:
	frappe.cache().set_value(_cache_key(connection), session, expires_in_sec=SESSION_TTL_SECONDS)


def clear_session(connection: str) -> None:
	"""Drop the in-flight credentials. Called on success, cancel and failure alike."""
	frappe.cache().delete_value(_cache_key(connection))


# --------------------------------------------------------------------------- #
# Flow
# --------------------------------------------------------------------------- #


def start(connection: str, login_credentials: list[dict], mode: str = "import") -> dict:
	"""Begin an import (or re-consent update) for a ``finAPI Bank Connection``.

	``login_credentials`` is finAPI's ``[{"label": ..., "value": ...}]`` shape, built
	from the labels the bank declares for the chosen interface.
	"""
	doc = frappe.get_doc("finAPI Bank Connection", connection)
	doc.check_permission("write")

	if mode == "import" and not doc.finapi_bank_id:
		frappe.throw(_("Set the finAPI Bank ID first (use the bank search)."))
	if mode == "update" and not doc.finapi_connection_id:
		frappe.throw(_("This connection has not been imported yet."))

	session = {
		"mode": mode,
		"finapi_user": doc.finapi_user,
		"bank_id": doc.finapi_bank_id,
		"connection_id": doc.finapi_connection_id,
		"interface": doc.interface or c.INTERFACE_XS2A,
		"login_credentials": login_credentials or [],
		"multi_step": None,
	}
	_store_session(connection, session)
	return _send(connection, session)


def submit_step(
	connection: str,
	two_step_procedure_id: str | None = None,
	challenge_response: str | None = None,
) -> dict:
	"""Answer the current SCA challenge (TAN scheme choice or the TAN itself)."""
	doc = frappe.get_doc("finAPI Bank Connection", connection)
	doc.check_permission("write")

	session = _load_session(connection)
	multi_step = dict(session.get("multi_step") or {})
	if not multi_step.get("hash"):
		frappe.throw(_("The authentication session is incomplete. Please start the import again."))

	# Only the stateful hash plus this step's answer go back — nothing else.
	step = {"hash": multi_step["hash"]}
	if two_step_procedure_id:
		step["twoStepProcedureId"] = two_step_procedure_id
	if challenge_response:
		step["challengeResponse"] = challenge_response

	session["multi_step"] = step
	_store_session(connection, session)
	return _send(connection, session)


def cancel(connection: str) -> dict:
	doc = frappe.get_doc("finAPI Bank Connection", connection)
	doc.check_permission("write")
	clear_session(connection)
	return {"state": "cancelled"}


def _send(connection: str, session: dict) -> dict:
	"""Fire one step at finAPI and translate the answer into a UI state."""
	client, token = get_user_session(session["finapi_user"])

	try:
		if session["mode"] == "update":
			payload = client.update_bank_connection(
				token=token,
				bank_connection_id=session["connection_id"],
				interface=session["interface"],
				login_credentials=session.get("login_credentials") or None,
				multi_step=session.get("multi_step"),
			)
		else:
			payload = client.import_bank_connection(
				token=token,
				bank_id=session["bank_id"],
				interface=session["interface"],
				login_credentials=session.get("login_credentials") or None,
				multi_step=session.get("multi_step"),
			)
	except ScaChallengeRequired as sca:
		# Expected: another step. Remember the running hash, ask the user.
		session["multi_step"] = dict(sca.multi_step or {})
		_store_session(connection, session)
		return _challenge_state(sca)
	except Exception:
		# A real failure — never leave credentials lying around.
		clear_session(connection)
		raise

	clear_session(connection)
	return _complete(connection, payload, token=token, client=client)


def _challenge_state(sca: ScaChallengeRequired) -> dict:
	"""Map a 510 onto what the dialog has to render next."""
	if sca.status == c.MS_TWO_STEP_PROCEDURE_REQUIRED:
		return {
			"state": "two_step",
			"procedures": sca.two_step_procedures,
			"message": sca.challenge_message,
		}

	if sca.status == c.MS_REDIRECT_REQUIRED:
		return {
			"state": "redirect",
			"redirect_url": (sca.multi_step or {}).get("redirectUrl"),
			"message": sca.challenge_message,
		}

	if sca.status == c.MS_DECOUPLED_AUTH_REQUIRED:
		return {"state": "decoupled", "message": sca.challenge_message}

	# CHALLENGE_RESPONSE_REQUIRED and anything else challenge-shaped.
	return {
		"state": "challenge",
		"message": sca.challenge_message,
		"answer_field_label": (sca.multi_step or {}).get("answerFieldLabel") or _("TAN"),
	}


# --------------------------------------------------------------------------- #
# Completion — persist the connection and map its accounts
# --------------------------------------------------------------------------- #


def _complete(connection: str, payload: dict, *, token: str, client) -> dict:
	doc = frappe.get_doc("finAPI Bank Connection", connection)

	connection_id = payload.get("id") or doc.finapi_connection_id
	doc.finapi_connection_id = str(connection_id) if connection_id else None
	doc.bank_name = payload.get("name") or (payload.get("bank") or {}).get("name") or doc.bank_name
	doc.status = "Connected"
	doc.last_error = None
	doc.consent_expiry = consent_expiry(payload)

	created = map_accounts(doc, client=client, token=token)
	doc.save()

	return {
		"state": "completed",
		"connection_id": doc.finapi_connection_id,
		"accounts": len(doc.accounts or []),
		"bank_accounts_linked": created,
	}


def consent_expiry(payload: dict):
	"""finAPI's consent expiry if it tells us one, else the PSD2 default of 90 days.

	finAPI has used several shapes and ISO-8601 with an offset, so anything unparseable
	falls back to the default rather than blowing up a finished authentication.
	"""
	for interface in payload.get("interfaces") or []:
		if not isinstance(interface, dict):
			continue

		consent = interface.get("aisConsent") or {}
		expiry = consent.get("expiresAt") or interface.get("consentExpiresAt")
		if not expiry:
			continue

		try:
			return get_datetime(str(expiry).replace("T", " ")[:19])
		except Exception:
			continue

	return add_days(now_datetime(), DEFAULT_CONSENT_DAYS)


def map_accounts(doc, *, client, token: str, include_removed: bool = False) -> int:
	"""Refresh the account child table from finAPI and link native Bank Accounts.

	Linking is by IBAN against existing ``Bank Account`` records — we deliberately do
	NOT create Bank Accounts, because a usable one needs a company GL account that only
	the accountant can choose. Unmatched accounts stay unlinked and are simply skipped
	by the sync until someone picks a Bank Account.
	"""
	accounts = [
		account
		for account in client.get_accounts(token=token)
		if str(account.get("bankConnectionId") or "") == str(doc.finapi_connection_id or "")
	]

	existing = {str(row.finapi_account_id): row for row in (doc.accounts or [])}
	known = _known_account_ids(doc)
	linked = 0

	for account in accounts:
		account_id = str(account.get("id"))
		row = existing.get(account_id)

		if row is None:
			# A row the user deleted must stay deleted. Private accounts have no business
			# in the company ledger, and silently resurrecting them on the next refresh
			# would undo that decision over and over. Accounts we have never seen are
			# genuinely new and do get added.
			if account_id in known and not include_removed:
				continue
			row = doc.append("accounts", {"finapi_account_id": account_id})

		row.account_name = account.get("accountName") or account.get("accountHolderName")
		# Banks love to name every account the same thing ("Sichteinlagen"), so the holder
		# is often the only clue which legal entity — which ERPNext Company — owns it.
		row.account_holder = account.get("accountHolderName")
		row.iban = account.get("iban")
		row.account_type = _account_type(account)
		row.currency = account.get("accountCurrency") or row.currency

		if not row.bank_account:
			row.bank_account = find_bank_account_by_iban(row.iban)

		if row.bank_account:
			linked += 1
			stamp_integration_id(row.bank_account, account_id)

	doc.known_account_ids = json.dumps(sorted(known | {str(a.get("id")) for a in accounts}))
	return linked


def _known_account_ids(doc) -> set[str]:
	try:
		return {str(i) for i in json.loads(doc.known_account_ids or "[]")}
	except (TypeError, ValueError):
		return set()


def _account_type(account: dict) -> str | None:
	"""finAPI has shipped ``accountType`` both as a plain enum and as an object."""
	account_type = account.get("accountType")
	if isinstance(account_type, dict):
		return account_type.get("name") or account_type.get("id")
	return account_type


def normalize_iban(iban: str | None) -> str:
	return (iban or "").replace(" ", "").upper()


def find_bank_account_by_iban(iban: str | None) -> str | None:
	"""Find a native Bank Account by IBAN, tolerating formatting differences."""
	wanted = normalize_iban(iban)
	if not wanted:
		return None

	for row in frappe.get_all("Bank Account", filters={"disabled": 0}, fields=["name", "iban"]):
		if normalize_iban(row.iban) == wanted:
			return row.name
	return None


def backfill_iban(bank_account: str, iban: str | None) -> None:
	"""Write the bank's IBAN onto a native ``Bank Account`` that has none.

	ERPNext Bank Accounts are routinely created without an IBAN, which is exactly why
	the automatic account match finds nothing and the first mapping has to be done by
	hand. Storing what the bank reported makes the record complete (ERPNext uses it for
	SEPA too) and lets every future account match itself.

	An IBAN that is already set is never overwritten — a mismatch means the mapping is
	wrong, and silently "fixing" the ledger's idea of the account would hide that.
	"""
	iban = normalize_iban(iban)
	if not iban:
		return

	current = normalize_iban(frappe.db.get_value("Bank Account", bank_account, "iban"))
	if not current:
		frappe.db.set_value("Bank Account", bank_account, "iban", iban)
		return

	if current != iban:
		frappe.msgprint(
			_(
				"Bank Account {0} has IBAN {1}, but the linked finAPI account is {2}. "
				"Please check the mapping — nothing was changed."
			).format(bank_account, current, iban),
			indicator="red",
			title=_("IBAN mismatch"),
		)


def stamp_integration_id(bank_account: str, finapi_account_id: str) -> None:
	"""Mirror the finAPI account id onto the native ``integration_id`` field.

	That is the field ERPNext's own bank feeds (Plaid) use, so the sync — and a future
	v16 unified bank-feed provider — can resolve an account without our child table.
	An id set by a different integration is left alone.
	"""
	current = frappe.db.get_value("Bank Account", bank_account, "integration_id")
	if current and current != finapi_account_id:
		frappe.msgprint(
			_("Bank Account {0} already carries a different Integration ID ({1}) — leaving it as is.").format(
				bank_account, current
			),
			indicator="orange",
		)
		return

	if not current:
		frappe.db.set_value("Bank Account", bank_account, "integration_id", finapi_account_id)

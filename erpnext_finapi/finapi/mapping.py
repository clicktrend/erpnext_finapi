# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""finAPI transaction ──▶ native ``Bank Transaction`` field mapping.

Deliberately Frappe-free: this is the whole provider-specific part of the feed, so it
stays unit-testable without a site and can be handed to ERPNext v16's unified bank-feed
interface ("give me transactions → map to Bank Transaction") as a thin adapter.
"""

from __future__ import annotations

import datetime

# Native Bank Transaction.transaction_id is shared by every bank feed, so we namespace
# ours. It is the deduplication key — do not change the prefix without a migration.
TRANSACTION_ID_PREFIX = "finapi:"


def transaction_id(finapi_transaction_id) -> str:
	"""The dedup key written to ``Bank Transaction.transaction_id``."""
	return f"{TRANSACTION_ID_PREFIX}{finapi_transaction_id}"


def parse_date(value) -> datetime.date | None:
	"""Parse a finAPI date (``YYYY-MM-DD``, tolerating a trailing time part)."""
	if not value:
		return None
	if isinstance(value, datetime.datetime):
		return value.date()
	if isinstance(value, datetime.date):
		return value
	try:
		return datetime.date.fromisoformat(str(value)[:10])
	except ValueError:
		return None


def parse_amount(value) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def map_transaction(transaction: dict, bank_account: str) -> dict:
	"""Return the ``Bank Transaction`` field dict for one finAPI transaction.

	Signs follow ERPNext: money in is a ``deposit``, money out a ``withdrawal``.

	We map **every** transaction, incoming and outgoing — filtering is reconciliation's
	job, not the feed's. (The predecessor system silently dropped everything outside
	``0 < amount <= 500``, which made the ledger incomplete by design.)
	"""
	amount = parse_amount(transaction.get("amount"))

	return {
		"doctype": "Bank Transaction",
		"date": parse_date(
			transaction.get("bankBookingDate")
			or transaction.get("valueDate")
			or transaction.get("finapiBookingDate")
		),
		"bank_account": bank_account,
		"deposit": amount if amount > 0 else 0.0,
		"withdrawal": -amount if amount < 0 else 0.0,
		"currency": transaction.get("currency"),
		"description": transaction.get("purpose") or transaction.get("counterpartName"),
		"reference_number": transaction.get("endToEndReference") or transaction.get("primanotaNumber"),
		"transaction_type": transaction.get("type"),
		"bank_party_name": transaction.get("counterpartName"),
		"bank_party_iban": transaction.get("counterpartIban"),
		"bank_party_account_number": transaction.get("counterpartAccountNumber"),
		"transaction_id": transaction_id(transaction.get("id")),
	}

# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Unit tests for the finAPI ──▶ ``Bank Transaction`` mapping."""

import datetime
import unittest

from erpnext_finapi.finapi.mapping import (
	TRANSACTION_ID_PREFIX,
	map_transaction,
	parse_amount,
	parse_date,
	transaction_id,
)

INCOMING = {
	"id": 6011,
	"accountId": 77,
	"amount": 119.0,
	"currency": "EUR",
	"purpose": "RE-2026-0042 Gravur",
	"counterpartName": "Muster GmbH",
	"counterpartIban": "DE02120300000000202051",
	"bankBookingDate": "2026-06-20",
	"valueDate": "2026-06-19",
	"type": "SEPA-Gutschrift",
	"endToEndReference": "E2E-1",
}

OUTGOING = {**INCOMING, "id": 6012, "amount": -49.9, "counterpartName": "Lieferant AG"}


class TestTransactionId(unittest.TestCase):
	def test_namespaced(self):
		# Bank Transaction.transaction_id is shared with every other feed.
		self.assertEqual(transaction_id(6011), f"{TRANSACTION_ID_PREFIX}6011")

	def test_stable_across_types(self):
		self.assertEqual(transaction_id(6011), transaction_id("6011"))


class TestParsing(unittest.TestCase):
	def test_date_formats(self):
		self.assertEqual(parse_date("2026-06-20"), datetime.date(2026, 6, 20))
		self.assertEqual(parse_date("2026-06-20 14:33:00"), datetime.date(2026, 6, 20))
		self.assertEqual(parse_date(datetime.date(2026, 6, 20)), datetime.date(2026, 6, 20))

	def test_bad_dates_are_none_not_crashes(self):
		self.assertIsNone(parse_date(None))
		self.assertIsNone(parse_date(""))
		self.assertIsNone(parse_date("not-a-date"))

	def test_amounts(self):
		self.assertEqual(parse_amount("119.00"), 119.0)
		self.assertEqual(parse_amount(None), 0.0)
		self.assertEqual(parse_amount("abc"), 0.0)


class TestMapping(unittest.TestCase):
	def test_incoming_is_a_deposit(self):
		row = map_transaction(INCOMING, "Sparkasse - Y&T")

		self.assertEqual(row["deposit"], 119.0)
		self.assertEqual(row["withdrawal"], 0.0)
		self.assertEqual(row["bank_account"], "Sparkasse - Y&T")
		self.assertEqual(row["doctype"], "Bank Transaction")

	def test_outgoing_is_a_positive_withdrawal(self):
		row = map_transaction(OUTGOING, "Sparkasse - Y&T")

		self.assertEqual(row["withdrawal"], 49.9)
		self.assertEqual(row["deposit"], 0.0)

	def test_no_amount_filter(self):
		# The predecessor silently dropped everything outside 0 < amount <= 500.
		big = map_transaction({**INCOMING, "id": 1, "amount": 5000.0}, "acc")
		self.assertEqual(big["deposit"], 5000.0)

	def test_booking_date_preferred_over_value_date(self):
		row = map_transaction(INCOMING, "acc")
		self.assertEqual(row["date"], datetime.date(2026, 6, 20))

	def test_falls_back_through_the_date_fields(self):
		row = map_transaction({"id": 1, "valueDate": "2026-05-05"}, "acc")
		self.assertEqual(row["date"], datetime.date(2026, 5, 5))

		row = map_transaction({"id": 1, "finapiBookingDate": "2026-04-04"}, "acc")
		self.assertEqual(row["date"], datetime.date(2026, 4, 4))

	def test_counterparty_and_reference_carried_over(self):
		row = map_transaction(INCOMING, "acc")

		self.assertEqual(row["bank_party_name"], "Muster GmbH")
		self.assertEqual(row["bank_party_iban"], "DE02120300000000202051")
		self.assertEqual(row["reference_number"], "E2E-1")
		self.assertEqual(row["description"], "RE-2026-0042 Gravur")
		self.assertEqual(row["transaction_id"], f"{TRANSACTION_ID_PREFIX}6011")

	def test_description_falls_back_to_counterparty(self):
		row = map_transaction({"id": 2, "counterpartName": "Nur Name"}, "acc")
		self.assertEqual(row["description"], "Nur Name")

	def test_sparse_transaction_does_not_crash(self):
		row = map_transaction({"id": 3}, "acc")

		self.assertEqual(row["deposit"], 0.0)
		self.assertEqual(row["withdrawal"], 0.0)
		self.assertIsNone(row["date"])
		self.assertEqual(row["transaction_id"], f"{TRANSACTION_ID_PREFIX}3")

	def test_only_known_bank_transaction_fields_are_produced(self):
		# Guard against typos that Frappe would silently ignore.
		allowed = {
			"doctype",
			"date",
			"bank_account",
			"deposit",
			"withdrawal",
			"currency",
			"description",
			"reference_number",
			"transaction_type",
			"bank_party_name",
			"bank_party_iban",
			"bank_party_account_number",
			"transaction_id",
		}
		self.assertEqual(set(map_transaction(INCOMING, "acc")), allowed)


if __name__ == "__main__":
	unittest.main()

# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""The feed hands new transactions to ERPNext's own Bank Transaction Rules (v16+).

Module-level on purpose (not inside a DocType folder): Frappe's runner would otherwise
auto-create global test records for every linked DocType and collide with a populated bench.
"""

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < v16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from erpnext_finapi import sync

PROBE = "finapi-rule-probe"
BANK = "_Test finAPI Bank"
BANK_ACCOUNT_NAME = "_Test finAPI Account"
RULE_NAME = "_Test finAPI rule"


def _company():
	return frappe.db.get_value("Company", {}, "name")


def _bank_gl_account(company):
	"""A leaf GL account of type Bank — created under the company's Bank Accounts group if
	the site has none (a fresh chart of accounts ships only the group)."""
	account = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name"
	)
	if account:
		return account

	group = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Bank", "is_group": 1}, "name"
	)
	if not group:
		return None

	return (
		frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "_Test finAPI Bank GL",
				"parent_account": group,
				"company": company,
				"account_type": "Bank",
				"is_group": 0,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _bank_account(company):
	name = f"{BANK_ACCOUNT_NAME} - {BANK}"
	if frappe.db.exists("Bank Account", name):
		return name

	if not frappe.db.exists("Bank", BANK):
		frappe.get_doc({"doctype": "Bank", "bank_name": BANK}).insert(ignore_permissions=True)

	gl_account = _bank_gl_account(company)
	if not gl_account:
		return None

	# One GL account may back only one Bank Account; reuse an existing holder if any.
	holder = frappe.db.get_value("Bank Account", {"account": gl_account}, "name")
	if holder:
		return holder

	return (
		frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": BANK_ACCOUNT_NAME,
				"bank": BANK,
				"is_company_account": 1,
				"company": company,
				"account": gl_account,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _rule(company):
	name = frappe.db.get_value("Bank Transaction Rule", {"rule_name": RULE_NAME, "company": company})
	if name:
		return name

	expense = frappe.db.get_value(
		"Account", {"company": company, "is_group": 0, "root_type": "Expense"}, "name"
	)
	if not expense:
		return None

	return (
		frappe.get_doc(
			{
				"doctype": "Bank Transaction Rule",
				"rule_name": RULE_NAME,
				"company": company,
				"transaction_type": "Any",
				"classify_as": "Bank Entry",
				"bank_entry_type": "Single Account",
				"account": expense,
				"description_rules": [{"check": "Contains", "value": PROBE}],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestRulesAfterSync(IntegrationTestCase):
	"""Mint's statement import runs the rules right after importing; the feed must too."""

	def setUp(self):
		if not frappe.db.exists("DocType", "Bank Transaction Rule"):
			self.skipTest("Bank Transaction Rule needs ERPNext v16")

		self.company = _company()
		if not self.company:
			self.skipTest("no Company on this site")

		self.bank_account = _bank_account(self.company)
		if not self.bank_account:
			self.skipTest("no usable Bank GL account on this site")

		self.currency = frappe.get_cached_value(
			"Account", frappe.db.get_value("Bank Account", self.bank_account, "account"), "account_currency"
		)

	def _feed_transaction(self, purpose, finapi_id):
		# Same entry point the sync uses, so the test exercises the real mapping and submit.
		return sync.create_bank_transaction(
			{
				"id": finapi_id,
				"amount": -12.5,
				"currency": self.currency,
				"purpose": purpose,
				"counterpartName": "Bank",
				"bankBookingDate": "2026-09-01",
				"type": "Entgelt",
			},
			self.bank_account,
		)

	def test_new_feed_transactions_are_classified(self):
		rule = _rule(self.company)
		if not rule:
			self.skipTest("no expense account for a rule on this site")

		hit = self._feed_transaction(f"Kontoführung {PROBE} September", 91001)
		miss = self._feed_transaction("Gutschrift Muster GmbH RE-2026-0042", 91002)
		self.assertIsNotNone(hit)
		self.assertIsNotNone(miss)

		self.assertTrue(sync.run_bank_transaction_rules(now=True))

		matched = frappe.db.get_value(
			"Bank Transaction", hit, ["is_rule_evaluated", "matched_transaction_rule"], as_dict=True
		)
		self.assertEqual(matched.is_rule_evaluated, 1)
		self.assertEqual(matched.matched_transaction_rule, rule)

		unmatched = frappe.db.get_value(
			"Bank Transaction", miss, ["is_rule_evaluated", "matched_transaction_rule"], as_dict=True
		)
		self.assertEqual(unmatched.is_rule_evaluated, 1)
		self.assertFalse(unmatched.matched_transaction_rule)

	def test_evaluation_is_idempotent(self):
		rule = _rule(self.company)
		if not rule:
			self.skipTest("no expense account for a rule on this site")

		name = self._feed_transaction(f"Entgelt {PROBE}", 91003)
		sync.run_bank_transaction_rules(now=True)
		# A second pass — the overlap window makes this the normal case — must not undo
		# or duplicate anything.
		sync.run_bank_transaction_rules(now=True)
		self.assertEqual(frappe.db.get_value("Bank Transaction", name, "matched_transaction_rule"), rule)

	def test_nothing_is_queued_without_rules(self):
		from unittest.mock import patch

		# Earlier tests in this class may have created a rule (rolled back only at class
		# end), so the "no rules" site is simulated instead of assumed.
		with patch.object(frappe.db, "count", return_value=0):
			self.assertFalse(sync.run_bank_transaction_rules(now=True))


class TestSyncConnectionWiring(IntegrationTestCase):
	"""``sync_connection`` queues the rules exactly when a run created transactions."""

	USER = "finapi-wiring-probe"

	def setUp(self):
		company = _company()
		if not company:
			self.skipTest("no Company on this site")

		if not frappe.db.exists("finAPI User", self.USER):
			frappe.get_doc(
				{
					"doctype": "finAPI User",
					"company": company,
					"environment": "Sandbox",
					"finapi_username": self.USER,
				}
			).insert(ignore_permissions=True)

		# No finapi_connection_id on purpose: stage one is skipped, only the read runs.
		self.connection = (
			frappe.get_doc(
				{
					"doctype": "finAPI Bank Connection",
					"connection_name": "_Test finAPI wiring",
					"finapi_user": self.USER,
					"sync_enabled": 1,
					"status": "Connected",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _run(self, fetched, created):
		from unittest.mock import patch

		with (
			patch.object(sync, "get_user_session", return_value=(object(), "token")),
			patch.object(sync, "_import_transactions", return_value=(fetched, created)),
			patch.object(sync, "run_bank_transaction_rules", return_value=True) as rules,
		):
			result = sync.sync_connection(self.connection, update_bank=False)
		return result, rules

	def test_rules_run_after_a_run_that_created_rows(self):
		result, rules = self._run(fetched=3, created=2)
		self.assertEqual(result["status"], "Success")
		self.assertEqual(result["created"], 2)
		rules.assert_called_once_with()

	def test_rules_do_not_run_when_nothing_was_created(self):
		result, rules = self._run(fetched=3, created=0)
		self.assertEqual(result["status"], "Success")
		rules.assert_not_called()

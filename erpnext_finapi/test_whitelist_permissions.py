# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < v16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings import test_connection
from erpnext_finapi.erpnext_finapi.doctype.finapi_user.finapi_user import register

UNPRIVILEGED = "finapi-permission-probe@example.com"


class TestfinAPIUser(IntegrationTestCase):
	"""The whitelisted helpers must refuse before they touch finAPI.

	@frappe.whitelist() only demands a session, so every one of these endpoints is
	reachable by any logged-in user — including portal users. Ordering matters as much
	as the check itself: register() creates a user at finAPI, and finAPI rejects a
	second creation, so a check that fires only on doc.save() would leave the record
	permanently unregisterable.
	"""

	def setUp(self):
		if not frappe.db.exists("User", UNPRIVILEGED):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": UNPRIVILEGED,
					"first_name": "finAPI Permission Probe",
					"send_welcome_email": 0,
					"roles": [],
				}
			).insert(ignore_permissions=True)

		company = frappe.db.get_value("Company", {}, "name")
		if not company:
			self.skipTest("no Company on this site")

		self.finapi_user = frappe.db.get_value("finAPI User", {"finapi_username": "probe-user"})
		if not self.finapi_user:
			doc = frappe.get_doc(
				{
					"doctype": "finAPI User",
					"company": company,
					"environment": "Sandbox",
					"finapi_username": "probe-user",
				}
			).insert(ignore_permissions=True)
			self.finapi_user = doc.name

		self.addCleanup(frappe.set_user, frappe.session.user)

	def test_register_refuses_an_unprivileged_caller(self):
		frappe.set_user(UNPRIVILEGED)
		# PermissionError rather than a network error proves the guard runs first: the
		# site has no finAPI credentials configured, so reaching the client at all would
		# raise something else entirely.
		with self.assertRaises(frappe.PermissionError):
			register(self.finapi_user)

	def test_register_is_reachable_for_an_authorized_caller(self):
		frappe.set_user("Administrator")
		doc = frappe.get_doc("finAPI User", self.finapi_user)
		# No assertion on the finAPI call itself — this only pins that the guard does not
		# reject the people who are supposed to get through.
		doc.check_permission("write")

	def test_test_connection_refuses_an_unprivileged_caller(self):
		frappe.set_user(UNPRIVILEGED)
		# finAPI Settings holds the mandator credentials; a whitelisted self-test on them
		# must not be a way for any logged-in user to probe them.
		with self.assertRaises(frappe.PermissionError):
			test_connection()

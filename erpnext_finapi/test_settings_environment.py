# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Sandbox and Live live side by side in finAPI Settings.

The environment is a property of whatever is being talked to, not a global mode: a finAPI
User picks one, and the settings supply the credentials of exactly that one. These tests
pin that wiring, because getting it wrong is silent — the wrong host answers 401 much
later, deep inside an SCA flow.
"""

import frappe

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # frappe < v16
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

from erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings import (
	configured_environments,
	get_client,
)
from erpnext_finapi.finapi import constants as c


class TestSettingsEnvironments(IntegrationTestCase):
	def setUp(self):
		settings = frappe.get_single("finAPI Settings")
		settings.environment = c.SANDBOX
		settings.sandbox_data_client_id = "sandbox-client"
		settings.sandbox_data_client_secret = "sandbox-secret"
		settings.live_data_client_id = ""
		settings.live_data_client_secret = ""
		settings.flags.ignore_permissions = True
		settings.save()

	def test_only_the_configured_environment_is_offered(self):
		self.assertEqual(configured_environments(), [c.SANDBOX])

	def test_client_uses_the_credentials_of_the_requested_environment(self):
		client = get_client(c.SANDBOX)
		self.assertEqual(client.api_host, c.API_HOSTS[c.SANDBOX])
		self.assertEqual(client.data_client_id, "sandbox-client")
		self.assertEqual(client.data_client_secret, "sandbox-secret")

	def test_missing_credentials_name_the_environment(self):
		# The old code silently used the one credential set for whatever was asked; now an
		# unconfigured environment says so, by name, before any request goes out.
		with self.assertRaises(frappe.ValidationError) as caught:
			get_client(c.LIVE)
		self.assertIn(c.LIVE, str(caught.exception))

	def test_no_argument_falls_back_to_the_default_environment(self):
		self.assertEqual(get_client().environment, c.SANDBOX)

	def test_a_live_user_no_longer_contradicts_a_sandbox_default(self):
		# What the old guard rejected outright: the settings default says Sandbox, the
		# record asks for Live. That is now merely a question of Live credentials.
		settings = frappe.get_single("finAPI Settings")
		settings.live_data_client_id = "live-client"
		settings.live_data_client_secret = "live-secret"
		settings.flags.ignore_permissions = True
		settings.save()

		client = get_client(c.LIVE)
		self.assertEqual(client.api_host, c.API_HOSTS[c.LIVE])
		self.assertEqual(client.data_client_id, "live-client")
		self.assertEqual(sorted(configured_environments()), sorted([c.SANDBOX, c.LIVE]))

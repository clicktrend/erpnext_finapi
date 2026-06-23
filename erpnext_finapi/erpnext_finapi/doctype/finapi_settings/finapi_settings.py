# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_finapi.finapi import constants as c
from erpnext_finapi.finapi.client import FinApiClient
from erpnext_finapi.finapi.exceptions import FinApiError


class finAPISettings(Document):
	def validate(self):
		# Keep the displayed hosts in lock-step with the environment (no drift).
		self.api_host = c.API_HOSTS.get(self.environment, "")
		self.webform_host = c.WEBFORM_HOSTS.get(self.environment, "")


def get_client() -> FinApiClient:
	"""Build a :class:`FinApiClient` from the singleton settings."""
	settings = frappe.get_single("finAPI Settings")
	if not settings.data_client_id:
		frappe.throw(_("finAPI Settings: the data client credentials are not configured."))

	admin_secret = settings.get_password("admin_client_secret") if settings.admin_client_secret else None
	return FinApiClient(
		environment=settings.environment,
		data_client_id=settings.data_client_id,
		data_client_secret=settings.get_password("data_client_secret"),
		admin_client_id=settings.admin_client_id or None,
		admin_client_secret=admin_secret,
	)


@frappe.whitelist()
def test_connection():
	"""Verify the configured data client credentials against finAPI."""
	try:
		result = get_client().test_connection()
		frappe.db.set_single_value(
			"finAPI Settings",
			"connection_status",
			f"OK — {result['environment']} ({result['api_host']})",
		)
		return {"ok": True, **result}
	except FinApiError as e:
		frappe.db.set_single_value("finAPI Settings", "connection_status", f"FAILED: {e}")
		return {"ok": False, "error": str(e), "status_code": e.status_code}

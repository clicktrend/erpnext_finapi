# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from erpnext_finapi.finapi import constants as c
from erpnext_finapi.finapi.client import FinApiClient
from erpnext_finapi.finapi.exceptions import FinApiError


class finAPISettings(Document):
	# Nothing to derive: the hosts are constants per environment (finapi.constants), and
	# both environments now live in this document side by side, so a single pair of
	# "current host" fields would have been a lie half the time.
	pass


def _check_permission() -> None:
	"""Guard the whitelisted helpers below.

	``@frappe.whitelist()`` only demands a session, and this document holds the mandator
	credentials — reading it must stay with the people who may write it.
	"""
	if not frappe.has_permission("finAPI Settings", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def configured_environments(settings=None) -> list[str]:
	"""Every environment that has a data client id stored, in Sandbox-then-Live order."""
	settings = settings or frappe.get_single("finAPI Settings")
	return [env for env in (c.SANDBOX, c.LIVE) if settings.get(f"{env.lower()}_data_client_id")]


@frappe.whitelist()
def environment_setup() -> dict:
	"""Which environments are usable, and which one a new record should default to.

	Read by the finAPI User form. Choosing an environment with no credentials behind it
	is the one mistake that stays invisible until the first API call, so the form says so
	up front. Guarded by finAPI User write permission rather than by the settings' own
	System-Manager-only permission: this exposes the two environment names, never a
	credential.
	"""
	if not frappe.has_permission("finAPI User", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	settings = frappe.get_single("finAPI Settings")
	return {
		"default": settings.environment,
		"configured": configured_environments(settings),
	}


def get_client(environment: str | None = None) -> FinApiClient:
	"""Build a :class:`FinApiClient` for one environment.

	Sandbox and Live are separate mandators with separate credentials *and* separate user
	pools, so the environment is never a global mode: it is a property of whatever is
	being talked to (a finAPI User, usually). Callers that genuinely have no context —
	the settings self-test — fall back to the configured default.
	"""
	settings = frappe.get_single("finAPI Settings")
	environment = environment or settings.environment

	if environment not in c.API_HOSTS:
		frappe.throw(_("Unknown finAPI environment {0}.").format(environment))

	prefix = environment.lower()
	client_id = settings.get(f"{prefix}_data_client_id")
	if not client_id:
		frappe.throw(
			_("finAPI Settings: no {0} credentials configured (the {0} Data Client ID is empty).").format(
				environment
			)
		)

	client_secret = settings.get_password(f"{prefix}_data_client_secret", raise_exception=False)
	if not client_secret:
		frappe.throw(_("finAPI Settings: the {0} Data Client Secret is empty.").format(environment))

	admin_client_id = settings.get(f"{prefix}_admin_client_id")
	admin_client_secret = (
		settings.get_password(f"{prefix}_admin_client_secret", raise_exception=False)
		if admin_client_id
		else None
	)

	return FinApiClient(
		environment=environment,
		data_client_id=client_id,
		data_client_secret=client_secret,
		admin_client_id=admin_client_id or None,
		admin_client_secret=admin_client_secret,
	)


@frappe.whitelist()
def test_connection(environment: str | None = None):
	"""Verify the stored client credentials against finAPI.

	Without an argument this tests *every* configured environment: with Sandbox and Live
	set up side by side, a green light for one of them says nothing about the other.
	"""
	_check_permission()

	environments = [environment] if environment else configured_environments()
	if not environments:
		frappe.throw(_("finAPI Settings: no credentials configured yet."))

	results, lines, ok = [], [], True
	for env in environments:
		try:
			result = get_client(env).test_connection()
			results.append({"ok": True, **result})
			lines.append(f"{env}: OK ({result['api_host']})")
		except FinApiError as e:
			ok = False
			results.append({"ok": False, "environment": env, "error": str(e), "status_code": e.status_code})
			lines.append(f"{env}: FAILED — {e}")

	frappe.db.set_single_value("finAPI Settings", "connection_status", "\n".join(lines))
	return {"ok": ok, "results": results}

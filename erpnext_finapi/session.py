# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Bridge between the Frappe DocTypes and the pure :mod:`erpnext_finapi.finapi` client.

Everything that needs to talk to finAPI *as a user* goes through :func:`get_user_session`,
so the credential handling and the environment guard live in exactly one place.
"""

from __future__ import annotations

import frappe
from frappe import _

from erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings import get_client
from erpnext_finapi.finapi.client import FinApiClient


def get_user_session(finapi_user: str) -> tuple[FinApiClient, str]:
	"""Return a client plus a USER access token for ``finapi_user``.

	A user token (password grant, issued by the DATA client) is what bank search,
	imports, updates and transaction reads need — a client token returns 403 there.

	The environment comes from the USER, not from a global setting: finAPI user pools are
	per mandator, a Sandbox user simply does not exist on the Live host. finAPI Settings
	holds the credentials of both environments side by side, so the two can never
	contradict each other — the user picks, the settings supply.
	"""
	user = frappe.get_doc("finAPI User", finapi_user)

	if not user.finapi_username:
		frappe.throw(_("finAPI User {0} has no username.").format(finapi_user))

	password = user.get_password("finapi_password") if user.finapi_password else None
	if not password:
		frappe.throw(_("finAPI User {0} has no password stored.").format(finapi_user))

	client = get_client(user.environment)
	token = client.authenticate_user(user.finapi_username, password)
	return client, token


# Berlin Group / PSD2 metadata. Their PRESENCE is what tells the bank a human is
# waiting for the answer — the bank cannot detect it, and finAPI forwards exactly
# these three headers.
PSU_IP_ADDRESS = "PSU-IP-Address"
PSU_USER_AGENT = "PSU-User-Agent"
PSU_DEVICE_OS = "PSU-Device-OS"

_OS_MARKERS = (
	("Windows", "Windows"),
	("Macintosh", "macOS"),
	("Mac OS", "macOS"),
	("Android", "Android"),
	("iPhone", "iOS"),
	("iPad", "iOS"),
	("Linux", "Linux"),
)


def psu_headers() -> dict | None:
	"""PSU metadata for the request currently being served — ``None`` in background jobs.

	PSD2 caps *unattended* bank updates at 4 per 24h and connection, but leaves
	user-triggered ones unlimited. The bank does not work out which is which: sending
	these headers is the declaration that a person asked for it.

	So this deliberately returns ``None`` whenever there is no HTTP request behind the
	call — a scheduled run must not claim a human. Callers that want the headers in a
	background job have to capture them in the web request and hand them over.
	"""
	request = getattr(frappe.local, "request", None)
	if not request:
		return None

	ip = getattr(frappe.local, "request_ip", None)
	if not ip:
		return None

	user_agent = request.headers.get("User-Agent") or ""
	device_os = next((name for marker, name in _OS_MARKERS if marker in user_agent), "unknown")

	return {
		PSU_IP_ADDRESS: ip,
		PSU_USER_AGENT: user_agent[:200] or "unknown",
		PSU_DEVICE_OS: device_os,
	}

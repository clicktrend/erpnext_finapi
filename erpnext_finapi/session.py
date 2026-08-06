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
	"""
	user = frappe.get_doc("finAPI User", finapi_user)
	settings = frappe.get_single("finAPI Settings")

	# finAPI user pools are per mandator: a Sandbox user simply does not exist on the
	# Live host. Catching that here turns a puzzling 401 into a clear message.
	if user.environment != settings.environment:
		frappe.throw(
			_("finAPI User {0} belongs to the {1} environment, but finAPI Settings is set to {2}.").format(
				finapi_user, user.environment, settings.environment
			)
		)

	if not user.finapi_username:
		frappe.throw(_("finAPI User {0} has no username.").format(finapi_user))

	password = user.get_password("finapi_password") if user.finapi_password else None
	if not password:
		frappe.throw(_("finAPI User {0} has no password stored.").format(finapi_user))

	client = get_client()
	token = client.authenticate_user(user.finapi_username, password)
	return client, token

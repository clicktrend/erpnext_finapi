# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from erpnext_finapi.erpnext_finapi.doctype.finapi_settings.finapi_settings import get_client


class finAPIUser(Document):
	pass


@frappe.whitelist()
def register(user: str):
	"""Register this user at finAPI (``POST /api/v2/users``, data client).

	Stores the returned finAPI user id and, if finAPI generated a password,
	persists it. Idempotent-ish: re-running on an already-registered user will
	attempt creation again, which finAPI rejects — guard in the UI.
	"""
	doc = frappe.get_doc("finAPI User", user)
	client = get_client()
	result = client.create_user(
		user_id=doc.finapi_username or None,
		password=doc.get_password("finapi_password") if doc.finapi_password else None,
	)
	doc.finapi_user_id = result.get("id") or doc.finapi_username
	if result.get("password") and not doc.finapi_password:
		doc.finapi_password = result["password"]
	doc.is_registered = 1
	doc.save()
	return {"ok": True, "user_id": doc.finapi_user_id}

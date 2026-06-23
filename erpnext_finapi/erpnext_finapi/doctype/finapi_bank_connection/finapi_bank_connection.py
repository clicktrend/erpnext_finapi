# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class finAPIBankConnection(Document):
	"""A bank connection imported from finAPI.

	The SCA import flow (direct multi-step / WebForm 2.0) that populates
	``finapi_connection_id`` and the ``accounts`` table is implemented in the
	import controller (Phase 1) — see wiki/SCA-Flows.md. Transaction sync into
	native ``Bank Transaction`` records lives in ``erpnext_finapi.tasks`` (Phase 2).
	"""

	pass

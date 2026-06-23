# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Scheduled tasks for erpnext_finapi.

The transaction sync (Phase 2) pulls new finAPI transactions into native
``Bank Transaction`` records. Until that is implemented, these are safe no-ops
that simply log intent, so enabling the scheduler hook never breaks a site.
"""

import frappe


def sync_all_bank_connections():
	"""Sync every active finAPI Bank Connection. Safe no-op until Phase 2."""
	if not frappe.db.exists("DocType", "finAPI Bank Connection"):
		return

	connections = frappe.get_all(
		"finAPI Bank Connection",
		filters={"status": "Connected"},
		pluck="name",
	)
	if not connections:
		return

	# TODO(Phase 2): for each connection, fetch transactions since last_sync via
	# FinApiClient and create native Bank Transaction records (dedup by finAPI id).
	# See docs/plans/2026-06-23-erpnext-finapi-banking-app.md §7 and wiki/Architecture.md.
	frappe.logger("erpnext_finapi").info(
		f"sync_all_bank_connections: {len(connections)} connection(s) pending sync implementation"
	)

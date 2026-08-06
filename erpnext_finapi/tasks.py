# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Scheduled tasks for erpnext_finapi.

The actual work lives in :mod:`erpnext_finapi.sync`; these are the thin entry points
the scheduler calls. Both are safe on a site that has no connection configured yet.
"""

import frappe

from erpnext_finapi import sync


def sync_all_bank_connections():
	"""Two-stage sync of every enabled connection (scheduled 4x/day).

	⚠️ Cadence is not cosmetic: PSD2 allows only 4 *unattended* bank updates per 24h and
	per connection. Running this more often makes the bank start rejecting stage one.
	"""
	if not frappe.db.exists("DocType", "finAPI Bank Connection"):
		return

	return sync.sync_all_connections()


def check_consent_expiry():
	"""Warn before a 90-day PSD2 consent lapses (daily)."""
	if not frappe.db.exists("DocType", "finAPI Bank Connection"):
		return

	return sync.check_consent_expiry()

# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

import frappe

# Who sees the app tile and the finAPI workspace: the people who own banking.
# Deliberately narrow — bank connections hold credentials and drive the ledger feed.
ADMIN_ROLES = {"System Manager", "Accounts Manager"}


def has_app_permission() -> bool:
	return bool(ADMIN_ROLES & set(frappe.get_roles()))

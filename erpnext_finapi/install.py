# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Install/migrate setup: the finAPI workspace and the /desk app tile.

Both are (re-)created on **every** migrate, not shipped as fixtures — Frappe creates
app tiles only in ``after_app_install``, so a site that migrates without reinstalling
would otherwise silently lose them.
"""

import json

import frappe

WORKSPACE = "finAPI"
WORKSPACE_ROLES = ["System Manager", "Accounts Manager"]

# The bank feed reads left to right: configure → connect → watch → reconcile.
WORKSPACE_SHORTCUTS = [
	{"label": "finAPI Settings", "link_to": "finAPI Settings", "type": "DocType"},
	{
		"label": "Bank Connections",
		"link_to": "finAPI Bank Connection",
		"type": "DocType",
		"doc_view": "List",
	},
	{"label": "finAPI Users", "link_to": "finAPI User", "type": "DocType", "doc_view": "List"},
	{"label": "Sync Log", "link_to": "finAPI Sync Log", "type": "DocType", "doc_view": "List"},
	# Native ERPNext from here on — this app only supplies the feed.
	{
		"label": "Bank Transactions",
		"link_to": "Bank Transaction",
		"type": "DocType",
		"doc_view": "List",
	},
	{
		"label": "Bank Reconciliation",
		"link_to": "bank-reconciliation-tool",
		"type": "Page",
	},
]


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	_ensure_workspace()
	_ensure_app_tile()


def _ensure_workspace():
	"""The finAPI workspace, restricted to the banking roles. Idempotent on migrate."""
	content = [
		{
			"id": "finapiHeader",
			"type": "header",
			"data": {"text": "<span class='h4'><b>finAPI Banking</b></span>", "col": 12},
		},
		{
			"id": "finapiIntro",
			"type": "paragraph",
			"data": {
				"text": (
					"Bank transactions are fetched from finAPI and written as native "
					"<b>Bank Transaction</b> records — reconcile them with the standard "
					"ERPNext tools."
				),
				"col": 12,
			},
		},
		{"id": "finapiSpacer", "type": "spacer", "data": {"col": 12}},
	]
	for index, shortcut in enumerate(WORKSPACE_SHORTCUTS):
		content.append(
			{
				"id": f"finapiShortcut{index}",
				"type": "shortcut",
				"data": {"shortcut_name": shortcut["label"], "col": 3},
			}
		)

	if frappe.db.exists("Workspace", WORKSPACE):
		doc = frappe.get_doc("Workspace", WORKSPACE)
	else:
		doc = frappe.new_doc("Workspace")
		doc.name = WORKSPACE

	doc.update(
		{
			"title": WORKSPACE,
			"label": WORKSPACE,
			"module": "ERPNext finAPI",
			"public": 1,
			"icon": "bank",
			"indicator_color": "green",
			"content": json.dumps(content),
		}
	)

	doc.set("shortcuts", [])
	for shortcut in WORKSPACE_SHORTCUTS:
		doc.append("shortcuts", shortcut)

	doc.set("roles", [])
	for role in WORKSPACE_ROLES:
		doc.append("roles", {"role": role})

	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save()


def _ensure_app_tile():
	"""Re-ensure the /desk app tile on every migrate.

	Frappe v16 builds app tiles in ``after_app_install`` only. A Desktop Icon is named
	after its label, so a workspace-derived icon can occupy the app tile's name and make
	the tile creation collide — drop such a stale icon first.
	"""
	from frappe.desk.doctype.desktop_icon.desktop_icon import create_desktop_icons_from_installed_apps

	app_title = frappe.get_hooks("app_title", app_name="erpnext_finapi")[0]
	stale_icon_type = frappe.db.get_value("Desktop Icon", app_title, "icon_type")
	if stale_icon_type and stale_icon_type != "App":
		frappe.delete_doc("Desktop Icon", app_title, ignore_permissions=True)

	create_desktop_icons_from_installed_apps()

	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")

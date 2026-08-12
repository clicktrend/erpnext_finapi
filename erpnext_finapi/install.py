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
	# Bank Reconciliation Tool is a single DocType, NOT a Page — a Page link passes the
	# workspace's loose shortcut check and then 404s on click.
	{
		"label": "Bank Reconciliation",
		"link_to": "Bank Reconciliation Tool",
		"type": "DocType",
	},
]


def after_install():
	setup()


def after_migrate():
	"""Never let cosmetics abort someone else's migration.

	``after_migrate`` runs for every app on every ``bench migrate`` — including core
	upgrades. If this hook raises (say a future Frappe adds a mandatory Workspace
	field), it does not merely cost a tile: it aborts the whole migration for the site.
	A missing workspace is repaired by the next migrate.
	"""
	try:
		setup()
	except Exception:
		frappe.log_error(title="erpnext_finapi: Workspace/Kachel-Setup übersprungen")


def setup():
	_ensure_workspace()
	_ensure_desk_entry()


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


def _ensure_desk_entry():
	"""Re-ensure the workspace sidebar *and* the /desk app tile on every migrate.

	Both are an ordering trap, not cosmetics. Frappe builds sidebars during
	``install-app``, *before* ``after_install`` runs, so a workspace created by an app's
	own install hook never gets one; the desktop icon that links to it then fails
	validation ("Could not find Link To"), and Frappe's own error handler raises on top
	of that, so the real cause is invisible. App tiles are likewise built in
	``after_app_install`` only, and nothing restores a missing one on migrate.

	Frappe's own ``after_app_install`` handler does exactly these two things, in exactly
	this order — so run that, resolved from its hooks, instead of importing the two
	underlying builders. Those have already moved once between releases
	(auto_generate_icons_and_sidebar -> create_desktop_icons_for_app, now gated behind
	is_desktop_icons_page), and this runs from ``after_migrate``: a hard import of a
	renamed symbol would abort ``bench migrate`` on every site, not merely cost a tile.
	Both builders are idempotent, and failures are logged rather than raised.

	A Desktop Icon is named after its label, so a workspace-derived icon can occupy the
	app tile's name and make the tile creation collide — drop such a stale icon first.
	"""
	app_title = frappe.get_hooks("app_title", app_name="erpnext_finapi")[0]
	stale_icon_type = frappe.db.get_value("Desktop Icon", app_title, "icon_type")
	if stale_icon_type and stale_icon_type != "App":
		frappe.delete_doc("Desktop Icon", app_title, ignore_permissions=True)

	try:
		for method in frappe.get_hooks("after_app_install", app_name="frappe"):
			frappe.get_attr(method)("erpnext_finapi")
	except Exception:
		frappe.log_error(title="erpnext_finapi: could not ensure the desk workspace entry")
		return

	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")

# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Move the single client credential set into its environment's fields.

Until 0.0.2 ``finAPI Settings`` held one pair of client credentials plus an
``environment`` switch that said which mandator they belonged to. Sandbox and Live now
sit side by side, so the old values have to land in the half the old switch named —
otherwise a site would come up looking configured while ``get_client()`` reads empty
fields.

Runs post model sync: the new fields must exist, and the old ones are gone from the
DocType by then. Their values survive in ``tabSingles`` / ``__Auth`` until the document
is saved for the first time (``update_single`` rewrites the whole row set), which is
exactly the window this patch uses.
"""

import frappe
from frappe.utils.password import get_decrypted_password, remove_encrypted_password

DOCTYPE = "finAPI Settings"
PLAIN_FIELDS = ("data_client_id", "admin_client_id")
SECRET_FIELDS = ("data_client_secret", "admin_client_secret")


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	# Read the raw rows: the old fields are gone from the DocType, so the document
	# object no longer exposes them.
	stored = frappe.db.get_singles_dict(DOCTYPE)

	environment = stored.get("environment")
	if environment not in ("Sandbox", "Live"):
		# No environment stored means nothing was ever configured here.
		return

	prefix = environment.lower()
	settings = frappe.get_single(DOCTYPE)
	moved = []

	for field in PLAIN_FIELDS:
		value = stored.get(field)
		target = f"{prefix}_{field}"
		# Never overwrite: a site that already filled in the new fields wins.
		if value and not settings.get(target):
			settings.set(target, value)
			moved.append(target)

	for field in SECRET_FIELDS:
		value = get_decrypted_password(DOCTYPE, DOCTYPE, field, raise_exception=False)
		target = f"{prefix}_{field}"
		if value and not settings.get_password(target, raise_exception=False):
			settings.set(target, value)
			moved.append(target)

	if not moved:
		return

	settings.flags.ignore_permissions = True
	settings.save()

	# The old secrets would otherwise stay decryptable in __Auth forever — saving only
	# clears the rows of fields the DocType still knows about.
	for field in SECRET_FIELDS:
		remove_encrypted_password(DOCTYPE, DOCTYPE, field)

	frappe.db.commit()
	print(f"erpnext_finapi: moved the {environment} client credentials into {', '.join(moved)}")

app_name = "erpnext_finapi"
app_title = "ERPNext finAPI"
app_publisher = "Adomio and contributors"
app_description = "Self-hosted finAPI bank-account integration for ERPNext — bring your own finAPI contract, sync transactions, reconcile natively."
app_email = "mitgravur@gmail.com"
app_license = "gpl-3.0"

# This app extends ERPNext (Bank, Bank Account, Bank Transaction, Bank Reconciliation Tool).
required_apps = ["erpnext"]

# App tile on the /desk launcher, leading to the finAPI workspace.
add_to_apps_screen = [
	{
		"name": "erpnext_finapi",
		"logo": "/assets/erpnext_finapi/logo.svg",
		"title": "ERPNext finAPI",
		"route": "/app/finapi",
		"has_permission": "erpnext_finapi.permissions.has_app_permission",
	}
]

# Scheduled tasks
# ---------------
# Pull new bank transactions from finAPI into native Bank Transaction records.
# The tasks are safe no-ops until at least one connection is configured.
#
# ⚠️ The 4x/day cadence is a PSD2 constraint, not a preference: unattended (PSU-absent)
# bank updates are capped at 4 per 24h and connection. Syncing more often makes the bank
# reject stage one — see erpnext_finapi/sync.py.
scheduler_events = {
	"cron": {
		"0 7,11,15,19 * * *": [
			"erpnext_finapi.tasks.sync_all_bank_connections",
		],
	},
	"daily": [
		"erpnext_finapi.tasks.check_consent_expiry",
	],
}

# Installation hooks
# ------------------
# The workspace and the /desk app tile are (re-)created on every migrate rather than
# shipped as fixtures: Frappe creates app tiles only in after_app_install, so a site
# that merely migrates would silently lose them.
after_install = "erpnext_finapi.install.after_install"
after_migrate = "erpnext_finapi.install.after_migrate"

# Test-site bootstrap: Frappe only runs the hook of the app under test, so a bare CI site
# would have no Company. No-op on a site that is already set up.
before_tests = "erpnext_finapi.testing.before_tests"

# Jinja / overrides / doc events are intentionally empty for now.

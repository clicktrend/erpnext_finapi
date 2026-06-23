app_name = "erpnext_finapi"
app_title = "ERPNext finAPI"
app_publisher = "Adomio and contributors"
app_description = "Self-hosted finAPI bank-account integration for ERPNext — bring your own finAPI contract, sync transactions, reconcile natively."
app_email = "mitgravur@gmail.com"
app_license = "gpl-3.0"

# This app extends ERPNext (Bank, Bank Account, Bank Transaction, Bank Reconciliation Tool).
required_apps = ["erpnext"]

# Scheduled tasks
# ---------------
# Pull new bank transactions from finAPI into native Bank Transaction records.
# The task is a safe no-op until at least one connection is configured.
scheduler_events = {
	"daily": [
		"erpnext_finapi.tasks.sync_all_bank_connections",
	],
}

# Fixtures (custom fields / roles) — added in a later phase.
# fixtures = []

# Installation hooks
# ------------------
# after_install = "erpnext_finapi.setup.install.after_install"

# Jinja / overrides / doc events are intentionally empty for now.

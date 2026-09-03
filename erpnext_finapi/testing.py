# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Test-site bootstrap.

``bench run-tests --app erpnext_finapi`` only runs the ``before_tests`` hook of the app
under test, so a bare CI site (``new-site`` + ``install-app``, setup wizard never run) has
no Company, no chart of accounts and no fiscal year — every integration test would skip.
On an already set-up site (a developer's bench) this is a deliberate no-op: real data is
never touched.
"""

import frappe
from frappe.utils import now_datetime


def before_tests():
	frappe.clear_cache()

	if frappe.get_all("Company", limit=1):
		return

	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = now_datetime().year
	# Same company name and abbreviation as ERPNext's own test records, so its fixtures
	# (``_Test Company`` / ``_TC``) line up if a test ever pulls them in.
	setup_complete(
		{
			"currency": "EUR",
			"full_name": "Test User",
			"company_name": "_Test Company",
			"timezone": "Europe/Berlin",
			"company_abbr": "_TC",
			"industry": "Services",
			"country": "Germany",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"language": "english",
			"company_tagline": "Testing",
			"email": "test@example.com",
			"password": "test",
			"chart_of_accounts": "Standard",
		}
	)
	frappe.db.commit()  # nosemgrep

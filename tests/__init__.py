# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Frappe-free unit tests — run with ``python -m unittest discover tests``.

They cover the two parts that carry the hard-won, live-verified finAPI knowledge:
the HTTP client (client roles, SCA shape, field names, paging) and the transaction
mapping. Neither needs a site, so CI can run them on every push.
"""

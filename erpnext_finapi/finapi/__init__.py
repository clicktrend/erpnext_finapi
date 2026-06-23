# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Pure finAPI Access V2 client library — no Frappe dependency.

This package encodes the hard-won, hardware-verified facts about finAPI Access
(client roles, live vs sandbox hosts, the V1/V2 mandator scope, and the 510
multi-step SCA flow). It is deliberately framework-agnostic so it can be unit
tested in isolation and reused outside Frappe.
"""

from erpnext_finapi.finapi.client import FinApiClient
from erpnext_finapi.finapi.exceptions import (
	FinApiAuthError,
	FinApiError,
	ScaChallengeRequired,
)

__all__ = [
	"FinApiAuthError",
	"FinApiClient",
	"FinApiError",
	"ScaChallengeRequired",
]

# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""finAPI Access V2 constants — hosts, endpoints, and status enums.

⚠️ Verified facts (do not "fix" without checking against finAPI live/sandbox):

* The WebForm host is ``webform-live.finapi.io`` / ``webform-sandbox.finapi.io``.
  ``webform.finapi.io`` DOES NOT EXIST (DNS fails) — a common misconfiguration.
* A mandator is scoped to ONE API version. A V1 mandator on ``/api/v2/*`` returns
  ``403 "client is limited to scope /api/v1"``. Switch with ``{"apiVersion": "V2"}``
  (reversible for 7 days).
* There are TWO client roles — see ``client.py``. Using the wrong one returns 403.
"""

# --- Environments -----------------------------------------------------------

SANDBOX = "Sandbox"
LIVE = "Live"

API_HOSTS = {
	SANDBOX: "https://sandbox.finapi.io",
	LIVE: "https://live.finapi.io",
}

# NOTE: there is NO "webform.finapi.io". Only the -sandbox / -live variants exist.
WEBFORM_HOSTS = {
	SANDBOX: "https://webform-sandbox.finapi.io",
	LIVE: "https://webform-live.finapi.io",
}


def api_host(environment: str) -> str:
	return API_HOSTS[environment]


def webform_host(environment: str) -> str:
	return WEBFORM_HOSTS[environment]


# --- Endpoints --------------------------------------------------------------

EP_TOKEN = "/api/v2/oauth/token"
EP_USERS = "/api/v2/users"
EP_BANKS = "/api/v2/banks"
EP_BANK_CONNECTIONS = "/api/v2/bankConnections"
EP_BANK_CONNECTIONS_IMPORT = "/api/v2/bankConnections/import"
EP_BANK_CONNECTIONS_UPDATE = "/api/v2/bankConnections/update"
EP_ACCOUNTS = "/api/v2/accounts"
EP_TRANSACTIONS = "/api/v2/transactions"
EP_WEBFORM_BANK_IMPORT = "/api/webForms/bankConnectionImport"
EP_WEBFORM = "/api/webForms/{web_form_id}"
# V1 endpoint, used by the admin client only, to flip mandator scope to V2.
EP_MANDATOR_SWITCH_VERSION = "/api/v1/mandatorAdmin/switchApiVersion"


# --- OAuth grant types ------------------------------------------------------

GRANT_CLIENT_CREDENTIALS = "client_credentials"
GRANT_PASSWORD = "password"


# --- Banking interfaces -----------------------------------------------------

INTERFACE_XS2A = "XS2A"
INTERFACE_FINTS_SERVER = "FINTS_SERVER"
INTERFACES = (INTERFACE_XS2A, INTERFACE_FINTS_SERVER)


# --- Multi-step (SCA) statuses ----------------------------------------------
# Returned inside the `multiStepAuthentication` object of a 510 response.

MS_TWO_STEP_PROCEDURE_REQUIRED = "TWO_STEP_PROCEDURE_REQUIRED"
MS_CHALLENGE_RESPONSE_REQUIRED = "CHALLENGE_RESPONSE_REQUIRED"
MS_REDIRECT_REQUIRED = "REDIRECT_REQUIRED"
MS_DECOUPLED_AUTH_REQUIRED = "DECOUPLED_AUTH_REQUIRED"


# --- WebForm 2.0 statuses ---------------------------------------------------

WF_NOT_YET_OPENED = "NOT_YET_OPENED"
WF_IN_PROGRESS = "IN_PROGRESS"
WF_COMPLETED = "COMPLETED"
WF_COMPLETED_WITH_ERROR = "COMPLETED_WITH_ERROR"
WF_ABORTED = "ABORTED"
WF_EXPIRED = "EXPIRED"

WF_TERMINAL = (WF_COMPLETED, WF_COMPLETED_WITH_ERROR, WF_ABORTED, WF_EXPIRED)


# --- Transactions -----------------------------------------------------------

# finAPI's "userView" returns the transaction as the user sees it (no bank-internal
# splitting). This is what the (verified) Marello importer used.
TX_VIEW_USER = "userView"

# finAPI caps a page at 500 entries. Anything above is silently clamped, so a
# single-page read is NOT a complete read — always follow `paging.pageCount`.
MAX_PER_PAGE = 500


# --- PSD2 / two-stage sync --------------------------------------------------

# ⚠️ Reading transactions is only stage TWO. finAPI does not poll the bank on its
# own schedule for us: a bank connection must be UPDATED (stage one, finAPI ← bank)
# or the read stays frozen on the last snapshot. This cost the predecessor system
# months of "0 imported, N skipped" — see client.update_bank_connection().
#
# PSD2 caps *unattended* (PSU-absent) updates at 4 per 24h per connection. User-present
# updates (someone clicking a button) are not capped.
PSD2_UNATTENDED_UPDATES_PER_DAY = 4

# finAPI downloads freshly fetched transactions slightly asynchronously — a read in
# the same run otherwise misses them.
POST_UPDATE_SETTLE_SECONDS = 15


# --- HTTP ------------------------------------------------------------------

# finAPI signals "another SCA step is required" with this non-standard status.
HTTP_ADDITIONAL_AUTHENTICATION_REQUIRED = 510

DEFAULT_TIMEOUT = 30

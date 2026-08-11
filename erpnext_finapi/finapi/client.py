# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""finAPI Access V2 HTTP client.

Framework-agnostic (no Frappe import). The Frappe layer wraps this client,
reading credentials from ``finAPI Settings`` / ``finAPI User`` and persisting
results into DocTypes.

The TWO CLIENT ROLES (a frequent source of 403s):

* **data client** — creates users (``POST /api/v2/users``), gets user tokens via
  the password grant, searches banks, runs webforms. Use ``authenticate_default_client()``
  and ``authenticate_user()``.
* **admin client** — ``/api/v2/mandatorAdmin/*`` and the V1 version switch ONLY.
  It cannot create users or search banks. Use ``authenticate_admin_client()``.

The SCA import is a stateful **510 multi-step** flow — see ``import_bank_connection``.
"""

from __future__ import annotations

import requests

from erpnext_finapi.finapi import constants as c
from erpnext_finapi.finapi.exceptions import (
	FinApiAuthError,
	FinApiError,
	ScaChallengeRequired,
)


def bank_search_term(search: str) -> str:
	"""Turn what a user naturally pastes into something the bank directory can match.

	Reaching for the IBAN is the obvious move — it is the number in front of you — but
	finAPI's directory only knows names, BICs and sort codes. A German IBAN carries the
	sort code in positions 5-12, so pull it out instead of answering "no bank found" to
	a perfectly good input.
	"""
	compact = (search or "").replace(" ", "").upper()

	if len(compact) == 22 and compact.startswith("DE") and compact[2:].isdigit():
		return compact[4:12]

	return search


class FinApiClient:
	"""A thin, typed wrapper over the finAPI Access V2 REST API."""

	def __init__(
		self,
		*,
		environment: str,
		data_client_id: str,
		data_client_secret: str,
		admin_client_id: str | None = None,
		admin_client_secret: str | None = None,
		timeout: int = c.DEFAULT_TIMEOUT,
		session: requests.Session | None = None,
	):
		if environment not in c.API_HOSTS:
			raise ValueError(f"Unknown environment {environment!r} (expected Sandbox or Live)")

		self.environment = environment
		self.api_host = c.api_host(environment)
		self.webform_host = c.webform_host(environment)

		self.data_client_id = data_client_id
		self.data_client_secret = data_client_secret
		self.admin_client_id = admin_client_id
		self.admin_client_secret = admin_client_secret

		self.timeout = timeout
		self._session = session or requests.Session()
		self._token_cache: dict[str, str] = {}

	# ------------------------------------------------------------------ #
	# Low-level request
	# ------------------------------------------------------------------ #

	def _url(self, path: str) -> str:
		return f"{self.api_host}{path}"

	def _request(
		self,
		method: str,
		path: str,
		*,
		token: str | None = None,
		json: dict | None = None,
		data: dict | None = None,
		params: dict | None = None,
		host: str | None = None,
		expect_sca: bool = False,
		psu_headers: dict | None = None,
	) -> dict:
		"""Perform a request and return the parsed JSON body.

		Raises :class:`FinApiAuthError` on 401/403, :class:`ScaChallengeRequired`
		on a 510 when ``expect_sca`` is set, and :class:`FinApiError` otherwise.
		"""
		url = f"{host}{path}" if host else self._url(path)
		headers = {"Accept": "application/json"}
		if token:
			headers["Authorization"] = f"Bearer {token}"
		if psu_headers:
			headers.update({k: v for k, v in psu_headers.items() if v})

		resp = self._session.request(
			method,
			url,
			headers=headers,
			json=json,
			data=data,
			params=params,
			timeout=self.timeout,
		)

		body = self._parse_body(resp)

		if resp.status_code == c.HTTP_ADDITIONAL_AUTHENTICATION_REQUIRED and expect_sca:
			self._raise_sca(body)

		if resp.status_code in (401, 403):
			raise FinApiAuthError(
				self._error_message(body) or "finAPI authentication/authorization failed",
				status_code=resp.status_code,
				response_body=body,
			)

		if not resp.ok:
			raise FinApiError(
				self._error_message(body) or f"finAPI request failed ({resp.status_code})",
				status_code=resp.status_code,
				response_body=body,
			)

		return body

	@staticmethod
	def _parse_body(resp: requests.Response) -> dict:
		try:
			return resp.json()
		except ValueError:
			return {"raw": resp.text}

	@staticmethod
	def _error_message(body: dict) -> str | None:
		"""Extract a human message from a finAPI error body."""
		if not isinstance(body, dict):
			return None
		errors = body.get("errors")
		if isinstance(errors, list) and errors:
			first = errors[0]
			if isinstance(first, dict):
				return first.get("message") or first.get("code")
		return body.get("error_description") or body.get("message")

	@staticmethod
	def _raise_sca(body: dict) -> None:
		"""Turn a 510 body into a :class:`ScaChallengeRequired`.

		⚠️ finAPI nests the ``multiStepAuthentication`` object inside ``errors[0]``
		(verified against the live mandator). A top-level variant is tolerated so a
		future API change does not silently turn every SCA step into a hard error.
		"""
		body = body or {}
		errors = body.get("errors")
		first_error = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}

		multi_step = first_error.get("multiStepAuthentication") or body.get("multiStepAuthentication") or {}

		raise ScaChallengeRequired(
			"Strong Customer Authentication required",
			multi_step=multi_step,
			# The procedure list lives inside multiStepAuthentication; older shapes put it on top.
			two_step_procedures=multi_step.get("twoStepProcedures") or body.get("twoStepProcedures") or [],
			challenge_message=multi_step.get("challengeMessage"),
			response_body=body,
		)

	# ------------------------------------------------------------------ #
	# Tokens
	# ------------------------------------------------------------------ #

	def _token(self, params: dict, cache_key: str) -> str:
		if cache_key in self._token_cache:
			return self._token_cache[cache_key]
		body = self._request("POST", c.EP_TOKEN, data=params)
		token = body.get("access_token")
		if not token:
			raise FinApiAuthError("finAPI did not return an access token", response_body=body)
		self._token_cache[cache_key] = token
		return token

	def authenticate_default_client(self) -> str:
		"""Client-credentials token for the DATA client (users, banks, webforms)."""
		return self._token(
			{
				"grant_type": c.GRANT_CLIENT_CREDENTIALS,
				"client_id": self.data_client_id,
				"client_secret": self.data_client_secret,
			},
			cache_key="data_client",
		)

	def authenticate_admin_client(self) -> str:
		"""Client-credentials token for the ADMIN client (mandatorAdmin only)."""
		if not (self.admin_client_id and self.admin_client_secret):
			raise FinApiAuthError("Admin client credentials are not configured")
		return self._token(
			{
				"grant_type": c.GRANT_CLIENT_CREDENTIALS,
				"client_id": self.admin_client_id,
				"client_secret": self.admin_client_secret,
			},
			cache_key="admin_client",
		)

	def authenticate_user(self, username: str, password: str) -> str:
		"""Password-grant token for a finAPI USER (issued by the data client)."""
		return self._token(
			{
				"grant_type": c.GRANT_PASSWORD,
				"client_id": self.data_client_id,
				"client_secret": self.data_client_secret,
				"username": username,
				"password": password,
			},
			cache_key=f"user:{username}",
		)

	def test_connection(self) -> dict:
		"""Verify the data client credentials by fetching a client token.

		Returns ``{"ok": True, "environment": ...}`` or raises ``FinApiError``.
		"""
		self.authenticate_default_client()
		return {"ok": True, "environment": self.environment, "api_host": self.api_host}

	# ------------------------------------------------------------------ #
	# Users (data client)
	# ------------------------------------------------------------------ #

	def create_user(
		self, *, user_id: str | None = None, password: str | None = None, email: str | None = None
	) -> dict:
		"""Create a finAPI user. Returns the created user (incl. id/password)."""
		token = self.authenticate_default_client()
		payload = {}
		if user_id:
			payload["id"] = user_id
		if password:
			payload["password"] = password
		if email:
			payload["email"] = email
		return self._request("POST", c.EP_USERS, token=token, json=payload)

	# ------------------------------------------------------------------ #
	# Banks (user or data token)
	# ------------------------------------------------------------------ #

	def search_banks(
		self,
		search: str,
		*,
		token: str,
		page: int = 1,
		per_page: int = 20,
		is_test_bank: bool | None = None,
	) -> dict:
		"""Search banks by name/BLZ/BIC.

		A full German IBAN is accepted and reduced to its sort code — see
		:func:`bank_search_term`.

		⚠️ Needs a USER token — a client token returns 403 UNAUTHORIZED_ACCESS.
		``is_test_bank`` filters finAPI's fake banks (wanted in Sandbox, noise in Live).
		"""
		params: dict = {"search": bank_search_term(search), "page": page, "perPage": per_page}
		if is_test_bank is not None:
			params["isTestBank"] = "true" if is_test_bank else "false"
		return self._request("GET", c.EP_BANKS, token=token, params=params)

	def get_bank(self, bank_id: int | str, *, token: str) -> dict:
		return self._request("GET", f"{c.EP_BANKS}/{bank_id}", token=token)

	# ------------------------------------------------------------------ #
	# Bank connection import — direct multi-step SCA
	# ------------------------------------------------------------------ #

	def import_bank_connection(
		self,
		*,
		token: str,
		bank_id: int | str,
		interface: str = c.INTERFACE_XS2A,
		login_credentials: list[dict] | None = None,
		multi_step: dict | None = None,
		account_types: list[str] | None = None,
		store_secrets: bool = True,
		psu_headers: dict | None = None,
	) -> dict:
		"""Import a bank connection, handling the stateful 510 SCA flow.

		On the first call pass ``login_credentials``. finAPI responds with a 510
		(raised as :class:`ScaChallengeRequired`) until SCA completes; carry its
		``multi_step`` (plus the user's procedure choice / TAN) into the next call.
		Returns the created bank connection on success (HTTP 2xx).

		``store_secrets`` lets finAPI keep the login credentials so later *unattended*
		updates (the scheduled sync's stage one) work without a human — without it the
		scheduler can never refresh the connection.

		⚠️ The full body — including ``login_credentials`` — must be re-sent on every
		step. Keep credentials server-side and transient (PSD2-sensitive).
		"""
		payload: dict = {
			"bankId": bank_id,
			"bankingInterface": interface,
			"storeSecrets": store_secrets,
		}
		if login_credentials:
			payload["loginCredentials"] = login_credentials
		if account_types:
			payload["accountTypes"] = account_types
		if multi_step:
			payload["multiStepAuthentication"] = multi_step

		return self._request(
			"POST",
			c.EP_BANK_CONNECTIONS_IMPORT,
			token=token,
			json=payload,
			expect_sca=True,
			psu_headers=psu_headers,
		)

	def update_bank_connection(
		self,
		*,
		token: str,
		bank_connection_id: int | str,
		interface: str = c.INTERFACE_XS2A,
		login_credentials: list[dict] | None = None,
		multi_step: dict | None = None,
		store_secrets: bool = True,
		psu_headers: dict | None = None,
	) -> dict:
		"""Make finAPI fetch fresh data FROM the bank — **stage one** of every sync.

		``get_transactions`` only reads finAPI's own store; it never triggers a bank
		fetch. Skipping this call leaves the data frozen on the snapshot taken at
		import time, and the sync reports "nothing new" forever.

		Within the 90-day consent window this usually succeeds *unattended* (finAPI
		replays the stored secrets). If the bank demands SCA anyway, a
		:class:`ScaChallengeRequired` is raised — a scheduler cannot answer a TAN, so
		callers should mark the connection as needing a manual update and move on.

		⚠️ **``psu_headers`` decides whether this counts against the PSD2 quota.** The
		bank does not detect whether a human triggered the call — it is declared, by
		the presence of the PSU metadata headers (see :func:`psu_headers`). Send them
		when a user is waiting for the result (unlimited), omit them in scheduled runs
		(capped at 4 per 24h and connection). Sending them from a cron would be a lie
		to the bank.

		⚠️ The field is ``bankingInterface`` — same as the import. finAPI's prose docs
		say ``interface``; sending that makes finAPI reject the whole body with
		"request contains no data / invalid JSON" (a 400 masquerading as an encoding bug).
		"""
		payload: dict = {
			"bankConnectionId": bank_connection_id,
			"bankingInterface": interface,
			"storeSecrets": store_secrets,
		}
		if login_credentials:
			payload["loginCredentials"] = login_credentials
		if multi_step:
			payload["multiStepAuthentication"] = multi_step

		return self._request(
			"POST",
			c.EP_BANK_CONNECTIONS_UPDATE,
			token=token,
			json=payload,
			expect_sca=True,
			psu_headers=psu_headers,
		)

	def get_bank_connections(self, *, token: str) -> list[dict]:
		"""All bank connections of the authenticated finAPI user."""
		body = self._request("GET", c.EP_BANK_CONNECTIONS, token=token)
		return body.get("connections") or []

	def get_bank_connection(self, bank_connection_id: int | str, *, token: str) -> dict:
		return self._request("GET", f"{c.EP_BANK_CONNECTIONS}/{bank_connection_id}", token=token)

	# ------------------------------------------------------------------ #
	# Accounts
	# ------------------------------------------------------------------ #

	def get_accounts(self, *, token: str, ids: list[int] | None = None) -> list[dict]:
		"""All accounts of the authenticated user (optionally filtered by finAPI id)."""
		params = {"ids": ",".join(str(i) for i in ids)} if ids else None
		body = self._request("GET", c.EP_ACCOUNTS, token=token, params=params)
		return body.get("accounts") or []

	# ------------------------------------------------------------------ #
	# WebForm 2.0
	# ------------------------------------------------------------------ #

	def create_import_webform(
		self,
		*,
		token: str,
		bank_id: int | str,
		account_types: list[str] | None = None,
		redirect_url: str | None = None,
	) -> dict:
		"""Create a finAPI-hosted import WebForm. Returns ``{id, url, status}``.

		The returned ``url`` lives on ``webform-(sandbox|live).finapi.io`` and is
		valid for ~20 minutes. Requires the WebForm 2.0 product to be enabled for
		the mandator (otherwise finAPI returns 403).
		"""
		payload: dict = {"bankId": bank_id}
		if account_types:
			payload["accountTypes"] = account_types
		if redirect_url:
			payload["redirectUrl"] = redirect_url
		return self._request(
			"POST",
			c.EP_WEBFORM_BANK_IMPORT,
			token=token,
			json=payload,
			host=self.api_host,
		)

	def get_webform_status(self, web_form_id: str | int, *, token: str) -> dict:
		"""Poll a WebForm's status (NOT_YET_OPENED … COMPLETED … EXPIRED)."""
		return self._request(
			"GET",
			c.EP_WEBFORM.format(web_form_id=web_form_id),
			token=token,
		)

	# ------------------------------------------------------------------ #
	# Transactions
	# ------------------------------------------------------------------ #

	def get_transactions_page(
		self,
		*,
		token: str,
		account_ids: list[int] | None = None,
		min_import_date: str | None = None,
		min_bank_booking_date: str | None = None,
		page: int = 1,
		per_page: int = c.MAX_PER_PAGE,
		view: str = c.TX_VIEW_USER,
	) -> dict:
		"""One page of transactions — the raw body incl. ``paging``.

		``min_import_date`` filters on when *finAPI* imported the transaction, which is
		the right incremental cursor: a transaction the bank booked days ago but
		delivered today still shows up. ``min_bank_booking_date`` filters on the bank's
		booking date instead. Both are ``YYYY-MM-DD``.
		"""
		params: dict = {"page": page, "perPage": min(per_page, c.MAX_PER_PAGE), "view": view}
		if account_ids:
			params["accountIds"] = ",".join(str(a) for a in account_ids)
		if min_import_date:
			params["minImportDate"] = min_import_date
		if min_bank_booking_date:
			params["minBankBookingDate"] = min_bank_booking_date
		return self._request("GET", c.EP_TRANSACTIONS, token=token, params=params)

	def get_transactions(
		self,
		*,
		token: str,
		account_ids: list[int] | None = None,
		min_import_date: str | None = None,
		min_bank_booking_date: str | None = None,
		per_page: int = c.MAX_PER_PAGE,
		view: str = c.TX_VIEW_USER,
		max_pages: int = 100,
	) -> list[dict]:
		"""ALL matching transactions, following finAPI's paging.

		⚠️ finAPI clamps ``perPage`` at 500, so reading page 1 only is a silent cap —
		on a busy account that quietly loses transactions. ``max_pages`` is a runaway
		guard, not a business limit.
		"""
		transactions: list[dict] = []
		page = 1
		while page <= max_pages:
			body = self.get_transactions_page(
				token=token,
				account_ids=account_ids,
				min_import_date=min_import_date,
				min_bank_booking_date=min_bank_booking_date,
				page=page,
				per_page=per_page,
				view=view,
			)
			batch = body.get("transactions") or []
			transactions.extend(batch)

			page_count = int((body.get("paging") or {}).get("pageCount") or 1)
			if page >= page_count or not batch:
				break
			page += 1

		return transactions

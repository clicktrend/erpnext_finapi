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
	) -> dict:
		"""Perform a request and return the parsed JSON body.

		Raises :class:`FinApiAuthError` on 401/403, :class:`ScaChallengeRequired`
		on a 510 when ``expect_sca`` is set, and :class:`FinApiError` otherwise.
		"""
		url = f"{host}{path}" if host else self._url(path)
		headers = {"Accept": "application/json"}
		if token:
			headers["Authorization"] = f"Bearer {token}"

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
		"""Turn a 510 body into a :class:`ScaChallengeRequired`."""
		multi_step = (body or {}).get("multiStepAuthentication") or {}
		raise ScaChallengeRequired(
			"Strong Customer Authentication required",
			multi_step=multi_step,
			two_step_procedures=(body or {}).get("twoStepProcedures") or [],
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

	def search_banks(self, search: str, *, token: str, page: int = 1, per_page: int = 20) -> dict:
		"""Search banks by name/BLZ/BIC."""
		return self._request(
			"GET",
			c.EP_BANKS,
			token=token,
			params={"search": search, "page": page, "perPage": per_page},
		)

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
	) -> dict:
		"""Import a bank connection, handling the stateful 510 SCA flow.

		On the first call pass ``login_credentials``. finAPI responds with a 510
		(raised as :class:`ScaChallengeRequired`) until SCA completes; carry its
		``multi_step`` (plus the user's procedure choice / TAN) into the next call.
		Returns the created bank connection on success (HTTP 2xx).

		⚠️ The full body — including ``login_credentials`` — must be re-sent on every
		step. Keep credentials server-side and transient (PSD2-sensitive).
		"""
		payload: dict = {
			"bankId": bank_id,
			"bankingInterface": interface,
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
		)

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

	def get_transactions(
		self,
		*,
		token: str,
		account_ids: list[int] | None = None,
		min_bank_booking_date: str | None = None,
		page: int = 1,
		per_page: int = 500,
	) -> dict:
		"""Fetch transactions (paged). ``min_bank_booking_date`` is ``YYYY-MM-DD``."""
		params: dict = {"page": page, "perPage": per_page}
		if account_ids:
			params["accountIds"] = ",".join(str(a) for a in account_ids)
		if min_bank_booking_date:
			params["minBankBookingDate"] = min_bank_booking_date
		return self._request("GET", c.EP_TRANSACTIONS, token=token, params=params)

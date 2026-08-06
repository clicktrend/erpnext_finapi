# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Unit tests for :class:`FinApiClient` against a fake HTTP session.

Every assertion here encodes a fact that was verified against a live finAPI mandator —
these are regression guards for mistakes that already cost real debugging time once.
"""

import json
import unittest

from erpnext_finapi.finapi import constants as c
from erpnext_finapi.finapi.client import FinApiClient
from erpnext_finapi.finapi.exceptions import FinApiAuthError, FinApiError, ScaChallengeRequired


class FakeResponse:
	def __init__(self, status_code=200, body=None, text=""):
		self.status_code = status_code
		self._body = body
		self.text = text
		self.ok = 200 <= status_code < 300

	def json(self):
		if self._body is None:
			raise ValueError("no json")
		return self._body


class FakeSession:
	"""Records requests and replays queued responses."""

	def __init__(self, responses=None):
		self.responses = list(responses or [])
		self.requests = []

	def request(self, method, url, *, headers=None, json=None, data=None, params=None, timeout=None):
		self.requests.append(
			{
				"method": method,
				"url": url,
				"headers": headers or {},
				"json": json,
				"data": data,
				"params": params or {},
			}
		)
		if not self.responses:
			return FakeResponse(200, {})
		return self.responses.pop(0)

	@property
	def last(self):
		return self.requests[-1]


TOKEN_RESPONSE = FakeResponse(200, {"access_token": "tok-123"})


def make_client(responses=None, environment=c.SANDBOX):
	session = FakeSession(responses)
	client = FinApiClient(
		environment=environment,
		data_client_id="data-id",
		data_client_secret="data-secret",
		admin_client_id="admin-id",
		admin_client_secret="admin-secret",
		session=session,
	)
	return client, session


class TestHostsAndEnvironment(unittest.TestCase):
	def test_hosts_per_environment(self):
		sandbox, _ = make_client(environment=c.SANDBOX)
		live, _ = make_client(environment=c.LIVE)

		self.assertEqual(sandbox.api_host, "https://sandbox.finapi.io")
		self.assertEqual(live.api_host, "https://live.finapi.io")

	def test_webform_host_is_never_the_nonexistent_bare_domain(self):
		# webform.finapi.io does not resolve — a classic misconfiguration.
		for environment in (c.SANDBOX, c.LIVE):
			client, _ = make_client(environment=environment)
			self.assertIn("webform-", client.webform_host)
			self.assertNotEqual(client.webform_host, "https://webform.finapi.io")

	def test_unknown_environment_rejected(self):
		with self.assertRaises(ValueError):
			FinApiClient(environment="Staging", data_client_id="a", data_client_secret="b")


class TestTokens(unittest.TestCase):
	def test_data_and_admin_clients_use_their_own_credentials(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {"access_token": "tok-admin"})])

		self.assertEqual(client.authenticate_default_client(), "tok-123")
		self.assertEqual(session.last["data"]["client_id"], "data-id")

		self.assertEqual(client.authenticate_admin_client(), "tok-admin")
		self.assertEqual(session.last["data"]["client_id"], "admin-id")

	def test_user_token_uses_password_grant_of_the_data_client(self):
		client, session = make_client([TOKEN_RESPONSE])

		client.authenticate_user("finapi-user", "pw")

		self.assertEqual(session.last["data"]["grant_type"], c.GRANT_PASSWORD)
		self.assertEqual(session.last["data"]["client_id"], "data-id")
		self.assertEqual(session.last["data"]["username"], "finapi-user")

	def test_tokens_are_cached(self):
		client, session = make_client([TOKEN_RESPONSE])

		client.authenticate_default_client()
		client.authenticate_default_client()

		self.assertEqual(len(session.requests), 1)

	def test_admin_client_without_credentials_fails_clearly(self):
		client = FinApiClient(
			environment=c.SANDBOX,
			data_client_id="data-id",
			data_client_secret="secret",
			session=FakeSession(),
		)
		with self.assertRaises(FinApiAuthError):
			client.authenticate_admin_client()

	def test_403_becomes_an_auth_error_with_the_finapi_message(self):
		client, _ = make_client(
			[FakeResponse(403, {"errors": [{"message": "client is limited to scope /api/v1"}]})]
		)
		with self.assertRaises(FinApiAuthError) as ctx:
			client.authenticate_default_client()

		self.assertIn("/api/v1", str(ctx.exception))
		self.assertEqual(ctx.exception.status_code, 403)


class TestScaFlow(unittest.TestCase):
	"""The 510 multi-step flow — the part that breaks silently when the shape is wrong."""

	def _sca_response(self, multi_step, nested=True):
		if nested:
			return FakeResponse(510, {"errors": [{"message": "SCA", "multiStepAuthentication": multi_step}]})
		return FakeResponse(510, {"multiStepAuthentication": multi_step})

	def test_multi_step_is_read_from_errors_zero(self):
		# ⚠️ finAPI nests multiStepAuthentication inside errors[0]. Reading only the
		# top level turns every SCA step into an unexplained error.
		multi_step = {
			"hash": "h-1",
			"status": c.MS_TWO_STEP_PROCEDURE_REQUIRED,
			"twoStepProcedures": [{"procedureId": "p1", "procedureName": "chipTAN"}],
		}
		client, _ = make_client([TOKEN_RESPONSE, self._sca_response(multi_step)])
		token = client.authenticate_default_client()

		with self.assertRaises(ScaChallengeRequired) as ctx:
			client.import_bank_connection(token=token, bank_id=274869)

		self.assertEqual(ctx.exception.hash, "h-1")
		self.assertEqual(ctx.exception.status, c.MS_TWO_STEP_PROCEDURE_REQUIRED)
		self.assertEqual(ctx.exception.two_step_procedures[0]["procedureId"], "p1")

	def test_top_level_multi_step_still_understood(self):
		multi_step = {"hash": "h-2", "status": c.MS_CHALLENGE_RESPONSE_REQUIRED, "challengeMessage": "TAN?"}
		client, _ = make_client([TOKEN_RESPONSE, self._sca_response(multi_step, nested=False)])
		token = client.authenticate_default_client()

		with self.assertRaises(ScaChallengeRequired) as ctx:
			client.import_bank_connection(token=token, bank_id=1)

		self.assertEqual(ctx.exception.challenge_message, "TAN?")

	def test_import_sends_bankinginterface_and_storesecrets(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(201, {"id": 42})])
		token = client.authenticate_default_client()

		client.import_bank_connection(
			token=token,
			bank_id=274869,
			interface=c.INTERFACE_XS2A,
			login_credentials=[{"label": "PIN", "value": "1234"}],
		)

		body = session.last["json"]
		self.assertEqual(body["bankingInterface"], c.INTERFACE_XS2A)
		self.assertNotIn("interface", body)
		# Without storeSecrets finAPI cannot run unattended updates later.
		self.assertTrue(body["storeSecrets"])

	def test_update_uses_bankinginterface_not_interface(self):
		# ⚠️ The prose docs say `interface`; the real model wants `bankingInterface`.
		# Sending the wrong name makes finAPI reject the body as "invalid JSON".
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {"id": 42})])
		token = client.authenticate_default_client()

		client.update_bank_connection(token=token, bank_connection_id=42)

		body = session.last["json"]
		self.assertEqual(session.last["url"], "https://sandbox.finapi.io" + c.EP_BANK_CONNECTIONS_UPDATE)
		self.assertEqual(body["bankConnectionId"], 42)
		self.assertIn("bankingInterface", body)
		self.assertNotIn("interface", body)

	def test_unattended_update_sends_no_credentials(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {})])
		token = client.authenticate_default_client()

		client.update_bank_connection(token=token, bank_connection_id=7)

		self.assertNotIn("loginCredentials", session.last["json"])

	def test_update_surfaces_sca_so_the_scheduler_can_skip(self):
		client, _ = make_client(
			[
				TOKEN_RESPONSE,
				FakeResponse(510, {"errors": [{"multiStepAuthentication": {"hash": "h", "status": "X"}}]}),
			]
		)
		token = client.authenticate_default_client()

		with self.assertRaises(ScaChallengeRequired):
			client.update_bank_connection(token=token, bank_connection_id=1)

	def test_genuine_error_is_not_mistaken_for_sca(self):
		client, _ = make_client([TOKEN_RESPONSE, FakeResponse(400, {"errors": [{"message": "bad request"}]})])
		token = client.authenticate_default_client()

		with self.assertRaises(FinApiError) as ctx:
			client.import_bank_connection(token=token, bank_id=1)

		self.assertNotIsInstance(ctx.exception, ScaChallengeRequired)
		self.assertIn("bad request", str(ctx.exception))


class TestTransactions(unittest.TestCase):
	def test_reads_every_page(self):
		# finAPI clamps perPage at 500 — stopping after page 1 silently loses data.
		pages = [
			FakeResponse(200, {"transactions": [{"id": 1}], "paging": {"page": 1, "pageCount": 3}}),
			FakeResponse(200, {"transactions": [{"id": 2}], "paging": {"page": 2, "pageCount": 3}}),
			FakeResponse(200, {"transactions": [{"id": 3}], "paging": {"page": 3, "pageCount": 3}}),
		]
		client, session = make_client([TOKEN_RESPONSE, *pages])
		token = client.authenticate_default_client()

		transactions = client.get_transactions(token=token, min_import_date="2026-01-01")

		self.assertEqual([t["id"] for t in transactions], [1, 2, 3])
		self.assertEqual([r["params"]["page"] for r in session.requests[1:]], [1, 2, 3])

	def test_incremental_cursor_is_min_import_date(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {"transactions": []})])
		token = client.authenticate_default_client()

		client.get_transactions(token=token, min_import_date="2026-06-01", account_ids=[1, 2])

		params = session.last["params"]
		self.assertEqual(params["minImportDate"], "2026-06-01")
		self.assertEqual(params["accountIds"], "1,2")
		self.assertEqual(params["view"], c.TX_VIEW_USER)
		self.assertLessEqual(params["perPage"], c.MAX_PER_PAGE)

	def test_per_page_is_clamped(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {"transactions": []})])
		token = client.authenticate_default_client()

		client.get_transactions_page(token=token, per_page=5000)

		self.assertEqual(session.last["params"]["perPage"], c.MAX_PER_PAGE)

	def test_stops_when_paging_missing(self):
		client, _ = make_client([TOKEN_RESPONSE, FakeResponse(200, {"transactions": [{"id": 1}]})])
		token = client.authenticate_default_client()

		self.assertEqual(len(client.get_transactions(token=token)), 1)


class TestBanksAndAccounts(unittest.TestCase):
	def test_bank_search_can_filter_test_banks(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {"banks": []})])
		token = client.authenticate_default_client()

		client.search_banks("WELADED1HAM", token=token, is_test_bank=False)

		self.assertEqual(session.last["params"]["isTestBank"], "false")
		self.assertEqual(session.last["params"]["search"], "WELADED1HAM")

	def test_accounts_unwrapped(self):
		client, _ = make_client([TOKEN_RESPONSE, FakeResponse(200, {"accounts": [{"id": 1}, {"id": 2}]})])
		token = client.authenticate_default_client()

		self.assertEqual(len(client.get_accounts(token=token)), 2)

	def test_connections_unwrapped(self):
		client, _ = make_client([TOKEN_RESPONSE, FakeResponse(200, {"connections": [{"id": 9}]})])
		token = client.authenticate_default_client()

		self.assertEqual(client.get_bank_connections(token=token)[0]["id"], 9)

	def test_bearer_token_is_sent(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {"accounts": []})])
		token = client.authenticate_default_client()

		client.get_accounts(token=token)

		self.assertEqual(session.last["headers"]["Authorization"], "Bearer tok-123")


class TestErrorParsing(unittest.TestCase):
	def test_non_json_body_does_not_crash(self):
		client, _ = make_client([FakeResponse(500, None, text="<html>oops</html>")])

		with self.assertRaises(FinApiError) as ctx:
			client.authenticate_default_client()

		self.assertEqual(ctx.exception.status_code, 500)
		self.assertEqual(ctx.exception.response_body, {"raw": "<html>oops</html>"})

	def test_missing_access_token_is_an_auth_error(self):
		client, _ = make_client([FakeResponse(200, {"token_type": "bearer"})])

		with self.assertRaises(FinApiAuthError):
			client.authenticate_default_client()

	def test_json_serialisable_error_body(self):
		client, _ = make_client([FakeResponse(400, {"errors": [{"message": "m", "code": 1}]})])

		with self.assertRaises(FinApiError) as ctx:
			client.authenticate_default_client()

		json.dumps(ctx.exception.response_body)


if __name__ == "__main__":
	unittest.main()


class TestBankSearchTerm(unittest.TestCase):
	"""The bank directory knows sort codes, not IBANs — but an IBAN is what users have."""

	def test_german_iban_yields_its_sort_code(self):
		from erpnext_finapi.finapi.client import bank_search_term

		self.assertEqual(bank_search_term("DE02120300000000202051"), "44160014")
		self.assertEqual(bank_search_term("DE02100500000054540402"), "41050095")

	def test_spaces_and_case_tolerated(self):
		from erpnext_finapi.finapi.client import bank_search_term

		self.assertEqual(bank_search_term("DE02120300000000202051"), "44160014")

	def test_plain_searches_pass_through(self):
		from erpnext_finapi.finapi.client import bank_search_term

		for value in ("Sparkasse Hamm", "WELADED1HAM", "41050095", ""):
			self.assertEqual(bank_search_term(value), value)

	def test_non_german_iban_passes_through(self):
		# Only DE encodes the sort code at 5-12; do not mangle others.
		from erpnext_finapi.finapi.client import bank_search_term

		self.assertEqual(bank_search_term("FR7630006000011234567890189"), "FR7630006000011234567890189")

	def test_search_banks_sends_the_reduced_term(self):
		client, session = make_client([TOKEN_RESPONSE, FakeResponse(200, {"banks": []})])
		token = client.authenticate_default_client()

		client.search_banks("DE02120300000000202051", token=token)

		self.assertEqual(session.last["params"]["search"], "44160014")

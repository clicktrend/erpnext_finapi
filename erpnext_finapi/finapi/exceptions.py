# Copyright (c) 2026, Adomio and contributors
# For license information, please see license.txt

"""Exceptions raised by the finAPI client."""


class FinApiError(Exception):
	"""Base error for any non-success finAPI response.

	Carries the HTTP status and the parsed response body (if any) so callers
	can surface a meaningful message instead of a raw traceback.
	"""

	def __init__(self, message, status_code=None, response_body=None):
		super().__init__(message)
		self.status_code = status_code
		self.response_body = response_body


class FinApiAuthError(FinApiError):
	"""Authentication / authorization failure (e.g. wrong client role → 403).

	Common causes:
	* Using the admin client for data operations, or vice versa.
	* A V1-scoped mandator hitting ``/api/v2/*`` ("client is limited to scope /api/v1").
	"""


class ScaChallengeRequired(FinApiError):
	"""A bank import needs another Strong Customer Authentication step (HTTP 510).

	This is NOT a failure — it is the expected, stateful SCA flow. The
	``multi_step`` dict (finAPI's ``multiStepAuthentication`` object, including the
	stateful ``hash``) plus any ``two_step_procedures`` / ``challenge_message`` must
	be carried back into the next ``import_bank_connection`` call.
	"""

	def __init__(
		self,
		message,
		*,
		multi_step=None,
		two_step_procedures=None,
		challenge_message=None,
		status_code=510,
		response_body=None,
	):
		super().__init__(message, status_code=status_code, response_body=response_body)
		self.multi_step = multi_step or {}
		self.two_step_procedures = two_step_procedures or []
		self.challenge_message = challenge_message

	@property
	def status(self):
		"""The ``multiStepAuthentication.status`` (e.g. CHALLENGE_RESPONSE_REQUIRED)."""
		return self.multi_step.get("status")

	@property
	def hash(self):
		"""The stateful hash that ties the SCA steps together."""
		return self.multi_step.get("hash")

# Contributing to erpnext_finapi

Thanks for your interest! This is a community project — issues, ideas and PRs are welcome.

## Ground rules

- **Sandbox first.** All development and testing happens against the **finAPI sandbox**.
  Never commit credentials, mandator ids, tokens, or PSD2 data.
- **Don't reinvent ERPNext.** This app is only the finAPI *feed*. Reconciliation, matching,
  payment entries and accounting stay native. If a feature belongs in ERPNext core, propose it there.
- **Security matters.** Bank credentials and TAN handling are sensitive. Keep PIN/TAN transient
  (server-side only, cleared after the flow). Flag anything security-relevant in your PR.

## Dev setup

```bash
bench get-app /path/to/erpnext_finapi      # or your fork's URL
bench --site dev.local install-app erpnext_finapi
bench --site dev.local migrate
bench --site dev.local console             # poke at FinApiClient interactively
```

Configure **finAPI Settings** with `Environment = Sandbox` and your sandbox client credentials.

## Code style

- Python: **ruff** (config in `pyproject.toml`) — tabs, 110 cols, double quotes (Frappe convention).
  Run `ruff check` and `ruff format` before committing.
- Code & comments in **English**. Keep controllers thin; put API logic in `erpnext_finapi/finapi/`.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`).

## Branching

- Branch off `develop`. PRs target `develop`. `main` is release-only.
- One logical change per PR. Reference the roadmap phase where relevant.

## Tests

- Unit-test `FinApiClient` against recorded/mocked HTTP responses (no live calls in CI).
- DocType controller logic should be covered where it carries behaviour.

## The finAPI traps (read before touching the client)

These are verified, hard-won facts encoded in `finapi/constants.py` and `finapi/client.py`:

- **Two client roles.** The *data* client creates users / searches banks / runs webforms; the
  *admin* client is `mandatorAdmin/*` only. Using the wrong one → `403`.
- **WebForm host is `webform-live.finapi.io`** (live) / `webform-sandbox.finapi.io` (sandbox).
  `webform.finapi.io` **does not exist**.
- **Mandator is scoped to one API version.** A V1 mandator on `/api/v2/*` → `403`.
  Switch with `{"apiVersion":"V2"}` (reversible for 7 days).
- **SCA is a `510` flow**, not an error. `POST /api/v2/bankConnections/import` returns
  `510 ADDITIONAL_AUTHENTICATION_REQUIRED` with `multiStepAuthentication`. Don't treat it as a failure.

See [wiki/SCA-Flows.md](wiki/SCA-Flows.md) for the full state machine.

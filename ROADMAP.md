# Roadmap

`erpnext_finapi` ships the finAPI **bank feed** for ERPNext. Everything from `Bank Transaction`
onward (reconciliation, payment entries, matching) is intentionally **native ERPNext** — not
re-implemented here.

Legend: ✅ done · 🚧 in progress · ⬜ planned

## Phase 1 — Foundation & connection ✅

- ✅ App skeleton, GPL-3.0, docs, wiki
- ✅ Data model: `finAPI Settings`, `finAPI User`, `finAPI Bank Connection` (+ account child),
  `finAPI Web Form`, `finAPI Sync Log`
- ✅ Core `FinApiClient` — client-role separation, host/version constants, token cache,
  bank search, `510` multi-step parsing
- ✅ **Test Connection** button (client-credentials token)
- ✅ Create `finAPI User` (data client), bank search UI
- ✅ **Direct multi-step SCA import** end-to-end (`TWO_STEP_PROCEDURE_REQUIRED` →
  `CHALLENGE_RESPONSE_REQUIRED` → `201`, plus redirect/decoupled), server-side state,
  credentials transient in cache only
- ✅ Accounts mapped to native `Bank Account` (by IBAN, or by hand) incl. `integration_id`
- ✅ **Discover Bank Connections** — adopt connections the finAPI user already owns
  instead of forcing a second consent

## Phase 2 — Sync & reconciliation ✅

- ✅ Scheduler sync → native `Bank Transaction`, deduplicated by `transaction_id` (`finapi:` prefix)
  + `finAPI Sync Log` per run
- ✅ **Two-stage sync** — `update_bank_connection` (finAPI ← bank) *then* read; reading alone
  freezes the feed on the import-time snapshot
- ✅ Manual **Sync Now**; `last_sync` cursor (`minImportDate` + overlap),
  native `Bank Account.last_integration_date`
- ✅ 90-day SCA re-consent: watchdog task, `Update Required` status, **Update Connection** flow
- ✅ Verified against a real live mandator: connection adopted, accounts mapped, real
  transactions written as submitted `Bank Transaction`s, re-run created 0 duplicates

## Phase 3 — WebForm 2.0 & live

- ⬜ WebForm 2.0 import incl. `allow_guest` callback + status polling
- ⬜ Live mandator support; redirect-URL whitelisting
- ✅ Live-verified read path (data-client token, user token, connections, accounts, paged
  transaction read) against a production mandator
- ⬜ Live SCA import against a real bank (interactive, real TAN)

> WebForm 2.0 stays blocked on finAPI enabling the product for the mandator (`403 Access Denied`).
> The client method exists; only the Frappe-side callback is missing.

## Phase 4 — Release & polish

- ✅ Unit tests for `FinApiClient` and the transaction mapping (Frappe-free, no site needed)
- ✅ CI runs lint, format, JSON validation, compile **and** the unit tests
- ⬜ Sandbox integration test (needs a sandbox mandator)
- ⬜ Frappe Cloud Marketplace listing / GitHub release
- ⬜ Translations (DE/EN)

> **Release gate:** the public GPL release is gated on **WebForm 2.0** (Phase 3). The direct
> multi-step flow accepts PIN/TAN server-side, which is fine for a self-hosted operator who owns
> the decision, but should not be shipped to the community as the default path.

## Phase 5 — v16 unified bank-feed interface (align when public)

ERPNext v16 merges [Mint](https://github.com/The-Commit-Company/mint) as the default banking
module and is adding a **unified bank-feed integration interface**: providers (Plaid, finAPI, …)
register a sync engine **via hooks**, the framework calls "give me transactions → map to
`Bank Transaction`", and the user gets **one** native sync button. This is the ideal docking point
for this app.

- ⬜ **Watch** the v16 unified bank-feed hook contract (provider registration API). *Not public yet —
  not present in our ERPNext 16.14 build; rolling out across v16 point releases.*
- ⬜ Register `erpnext_finapi` as a `finapi` bank-feed provider via that hook (keep our own
  scheduler/sync as the fallback). Our `FinApiClient` is already provider-shaped, so this
  should be a thin adapter — **design Phase 2 sync to make this trivial.**

> We already run on **v16** (Frappe 16.15 / ERPNext 16.14). Today the sync writes native
> `Bank Transaction`s directly (own sync button + scheduler) and reconciles with the native Bank
> Reconciliation Tool; once the unified bank-feed hook lands in v16 we register as a provider.

## Phase 6 — Optional / later

- ⬜ Second provider layer: **EBICS** (no 90-day re-consent) behind the same client abstraction
- ⬜ Payment Initiation (PIS) → confirm outbound `Payment Entry` (touches the gateway side; separate)

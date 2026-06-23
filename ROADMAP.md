# Roadmap

`erpnext_finapi` ships the finAPI **bank feed** for ERPNext. Everything from `Bank Transaction`
onward (reconciliation, payment entries, matching) is intentionally **native ERPNext** — not
re-implemented here.

Legend: ✅ done · 🚧 in progress · ⬜ planned

## Phase 1 — Foundation & connection (MVP, sandbox)

- ✅ App skeleton, GPL-3.0, docs, wiki
- ✅ Data model: `finAPI Settings`, `finAPI User`, `finAPI Bank Connection` (+ account child),
  `finAPI Web Form`, `finAPI Sync Log`
- ✅ Core `FinApiClient` — client-role separation, host/version constants, token cache,
  bank search, `510` multi-step parsing
- 🚧 **Test Connection** button (client-credentials token against sandbox)
- 🚧 Create `finAPI User` (data client), bank search UI
- 🚧 **Direct multi-step SCA import** end-to-end against the finAPI **sandbox**
  → creates `finAPI Bank Connection` + maps accounts to ERPNext `Bank Account`

## Phase 2 — Sync & reconciliation

- ⬜ Scheduler sync → native `Bank Transaction` (dedup by finAPI transaction id) + `finAPI Sync Log`
- ⬜ Manual "Sync now" action; `last_sync` / `consent_expiry` handling
- ⬜ 90-day SCA re-consent notification + re-connect flow
- ⬜ Verify imported transactions reconcile in the **native** Bank Reconciliation Tool

## Phase 3 — WebForm 2.0 & live

- ⬜ WebForm 2.0 import incl. `allow_guest` callback + status polling
- ⬜ Live mandator support; redirect-URL whitelisting
- ⬜ Live verification against a real bank (interactive, real TAN)

## Phase 4 — Release & polish

- ⬜ Test suite (unit tests for `FinApiClient` against recorded fixtures)
- ⬜ CI green, sandbox integration test
- ⬜ Frappe Cloud Marketplace listing / GitHub release
- ⬜ Translations (DE/EN)

## Phase 5 — Optional / later

- ⬜ Second provider layer: **EBICS** (no 90-day re-consent) behind the same client abstraction
- ⬜ Payment Initiation (PIS) → confirm outbound `Payment Entry` (touches the gateway side; separate)

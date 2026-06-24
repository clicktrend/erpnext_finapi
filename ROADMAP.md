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

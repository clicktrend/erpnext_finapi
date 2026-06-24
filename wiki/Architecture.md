# Architecture

## Principle: feed only, reconcile natively

`erpnext_finapi` adds **one** thing ERPNext lacks for the German/EU market: a finAPI bank feed.
Everything downstream is native ERPNext.

```
┌────────────┐  AIS / PSD2   ┌──────────────────┐   writes     ┌──────────────────┐
│  finAPI    │◀──────────────│  erpnext_finapi  │─────────────▶│ Bank Transaction │  (native)
│  Access V2 │  BYO contract │                  │  dedup by    │                  │
└────────────┘               │  • SCA import    │  finapi id   └────────┬─────────┘
                             │  • scheduler sync│                       │ native
                             └──────────────────┘            ┌──────────▼───────────────┐
                                                             │ Bank Reconciliation Tool │
                                                             │  → Payment Entry → clears│
                                                             │     Invoice / Journal    │
                                                             └──────────────────────────┘
```

This mirrors ERPNext's own **Plaid** integration (aggregator → auto-create `Bank Transaction` →
native reconciliation). We are "Plaid, but finAPI", for German banks.

## Two meanings of "payments" in ERPNext

finAPI belongs to exactly one:

| Surface | Direction | Purpose | This app |
|---|---|---|---|
| Payment Gateway (`payments` app) | outbound | customers pay you online (Stripe/PayPal/…) | ❌ |
| **Bank Transaction + Reconciliation** | inbound | read account activity, match vouchers | ✅ |

## Components

```
erpnext_finapi/
├── finapi/                      ← pure client library (no Frappe import, unit-testable)
│   ├── constants.py             hosts, endpoints, status enums (the verified facts)
│   ├── exceptions.py            FinApiError, FinApiAuthError, ScaChallengeRequired
│   └── client.py                FinApiClient — roles, tokens, 510 multi-step, transactions
├── tasks.py                     scheduler: sync → Bank Transaction (Phase 2)
└── erpnext_finapi/doctype/
    ├── finapi_settings/         Single: mandator, clients, hosts, Test Connection
    ├── finapi_user/             Company ↔ finAPI user (password-grant identity)
    ├── finapi_bank_connection/  imported connection (+ account child → Bank Account)
    │   └── finapi_bank_connection_account/
    ├── finapi_web_form/         WebForm 2.0 session tracking
    └── finapi_sync_log/         per-run audit
```

The **client library is deliberately Frappe-free** so it can be tested against recorded HTTP
responses and reused outside ERPNext. The DocType controllers are thin wrappers that read
encrypted credentials and persist results.

## Data mapping

A finAPI transaction becomes a native `Bank Transaction`:

| finAPI | Bank Transaction |
|---|---|
| `id` | `finapi_transaction_id` (dedup key) |
| `bankBookingDate` | `date` |
| `amount` (sign) | `deposit` / `withdrawal` |
| `purpose` / `counterpartName` | `description` / `bank_party_name` |
| account → mapped Bank Account | `bank_account` |

Native ERPNext then handles matching (incl. automatic & fuzzy party matching) and clearing.

## Why a separate, self-hosted app

The dominant Frappe banking app routes bank access through a paid SaaS backend and does not let
you bring your own aggregator credentials. `erpnext_finapi` is the **self-hosted, BYO-finAPI**
alternative — you pay finAPI directly (sandbox free), and there is no middleman.

> Concept/background (German): `docs/plans/2026-06-23-erpnext-finapi-banking-app.md` in the parent
> project.

## Forward: ERPNext v16 unified bank-feed interface

ERPNext **v16** adds [Mint](https://github.com/The-Commit-Company/mint) as the default banking
module (consolidated reconciliation, rules, a heuristic CSV/Excel statement importer) and a
**unified bank-feed integration interface**: a provider registers a sync engine **via hooks**, the
framework asks it for transactions and maps them to `Bank Transaction`, and the user gets **one**
native sync button (Plaid, finAPI, regional banks all behind the same button). *(Announced; rolling
out across v16 point releases — not yet present in 16.14.)*

This app already targets **v16** (Frappe 16.15 / ERPNext 16.14). `FinApiClient` is already
provider-shaped (call API → get transactions → map), so the sync layer is kept deliberately thin:
today it writes `Bank Transaction` directly, and once the unified bank-feed hook lands it registers
as a `finapi` provider with a small adapter. The Mint merge also reinforces the core rule here —
**we never reimplement reconciliation**; we only supply the feed. See [Roadmap](Roadmap) Phase 5.

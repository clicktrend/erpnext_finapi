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
│   ├── client.py                FinApiClient — roles, tokens, 510 multi-step, transactions
│   └── mapping.py               finAPI transaction → Bank Transaction fields
├── session.py                   user token per finAPI User (+ Sandbox/Live guard)
├── sca.py                       server-side SCA state machine (import & re-consent)
├── sync.py                      two-stage sync, dedup, Sync Log, consent watchdog
├── tasks.py                     scheduler entry points
└── erpnext_finapi/doctype/
    ├── finapi_settings/         Single: mandator, clients, hosts, sync window, Test Connection
    ├── finapi_user/             Company ↔ finAPI user (password grant, connection discovery)
    ├── finapi_bank_connection/  connection + wizard (+ account child → Bank Account)
    │   └── finapi_bank_connection_account/
    ├── finapi_web_form/         WebForm 2.0 session tracking
    └── finapi_sync_log/         per-run audit
```

The **client library and the mapping are deliberately Frappe-free** so they can be tested without
a site (`python -m unittest discover -s tests`, run in CI) and reused outside ERPNext. The DocType
controllers are thin wrappers that read encrypted credentials and persist results.

## The sync has two stages

This is the single most important thing to know about the feed:

```
Stage 1   update_bank_connection()    finAPI ◀── bank    fetch fresh data
Stage 2   get_transactions()          us     ◀── finAPI  read what finAPI holds
```

**Reading alone never fails loudly.** finAPI does not poll your bank on our behalf, so a sync that
only reads keeps returning the snapshot taken at import time and reports "nothing new" forever
while the account fills up. Stage 1 is what makes the feed live.

Stage 1 normally runs *unattended* — finAPI replays the credentials stored at import time
(`storeSecrets`). If the bank demands SCA anyway, the connection is flagged `Update Required` and a
human runs **Update Connection**; the sync still reads whatever finAPI already has.

> **PSD2 caps unattended updates at 4 per 24h and connection.** The scheduler therefore runs
> 4×/day (`0 7,11,15,19`). User-present updates (someone clicking a button) are not capped.

## Data mapping

A finAPI transaction becomes a native `Bank Transaction` (see `finapi/mapping.py`):

| finAPI | Bank Transaction |
|---|---|
| `id` | `transaction_id`, prefixed `finapi:` — **the dedup key** |
| `bankBookingDate` → `valueDate` → `finapiBookingDate` | `date` |
| `amount` (sign) | `deposit` / `withdrawal` |
| `currency` | `currency` |
| `purpose` (falls back to `counterpartName`) | `description` |
| `counterpartName` / `counterpartIban` / `counterpartAccountNumber` | `bank_party_*` |
| `type` | `transaction_type` |
| `endToEndReference` → `primanotaNumber` | `reference_number` |
| account → linked Bank Account | `bank_account` |

We use the **native** `transaction_id` field rather than a custom one, namespaced with a `finapi:`
prefix because that field is shared with every other bank feed. Records are inserted **and
submitted**, so they appear in the Bank Reconciliation Tool immediately.

Every sync re-reads a small overlap window on purpose (duplicates cost nothing, gaps are silent) —
the dedup key is what makes that safe. **No amount filtering happens in the feed**: incoming and
outgoing transactions are all imported, because filtering is reconciliation's job.

Accounts are linked to native `Bank Account` records by **IBAN**. We never create Bank Accounts —
a usable one needs a company GL account only the accountant can choose. Note that ERPNext Bank
Accounts often have no IBAN stored, in which case you link them by hand in the connection's account
table; either way the finAPI account id is mirrored onto the native `Bank Account.integration_id`.

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

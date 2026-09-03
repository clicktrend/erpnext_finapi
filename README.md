# erpnext_finapi

**Self-hosted [finAPI](https://www.finapi.io/) bank-account integration for ERPNext — bring your own finAPI contract, sync transactions, reconcile natively.**

> ⚠️ **Status: Beta.** The feed is complete and works: SCA bank import, account mapping, and the two-stage scheduled sync into native `Bank Transaction`s. The read and write path is verified against a **production** finAPI mandator (real connection, real transactions, no duplicates on re-run). Still open: the finAPI-hosted **WebForm 2.0** flow (blocked on finAPI enabling the product) and a live SCA import with a real TAN. See [ROADMAP.md](ROADMAP.md).
>
> The direct SCA flow accepts PIN/TAN **on your own server** (transient, cache-only, never stored). That is a deliberate self-hosted trade-off — read [SCA Flows](wiki/SCA-Flows.md) before using it in production.

---

## What it does

`erpnext_finapi` connects your German/EU bank accounts to ERPNext via the **finAPI Access** PSD2/XS2A API and feeds real bank transactions into ERPNext's **native** accounting stack:

```
 finAPI Access ──▶  erpnext_finapi  ──▶  Bank Transaction  ──▶  Bank Reconciliation Tool
  (your contract)    (this app)          (native ERPNext)        (native ERPNext)
                                                                  → Payment Entry → clears Invoice
```

It is, in essence, **"the ERPNext Plaid integration, but with finAPI"** — same target DocTypes, same reconciliation, built for the German market (Sparkassen, Volksbanken, chipTAN/SCA, FinTS).

## Where it fits in ERPNext (important)

ERPNext uses the word *"payments"* for two unrelated things. finAPI belongs to **one** of them:

| Native ERPNext surface | Direction | Purpose | This app? |
|---|---|---|---|
| **Payment Gateway** (`payments` app: Stripe, PayPal, Razorpay, GoCardless) | outbound | let customers pay *you* online | ❌ no |
| **Bank Transaction + Bank Reconciliation Tool** (Accounting core) | inbound | read what hit your account, match against vouchers | ✅ **yes** |

finAPI is an **Account Information Service (AIS)** — it *reads* what happened on your bank account. This app writes native `Bank Transaction` records and lets ERPNext's built-in reconciliation (incl. automatic & fuzzy party matching) do the rest. **We do not reinvent matching, reconciliation, or payment entries.**

## Why this app exists

The well-known [ALYF Banking](https://github.com/alyf-de/banking) app is excellent but is, at its core, a **SaaS client**: bank access (Klarna Kosma / EBICS) is routed through ALYF's own hosted backend on a paid per-account subscription, and you **cannot bring your own aggregator credentials**.

`erpnext_finapi` fills the gap: a **self-hosted, bring-your-own-finAPI-contract** connector. No middleman, no per-account SaaS fee — you pay finAPI directly (and finAPI's **sandbox is free**, so the community can test without a contract).

| | ALYF Banking | **erpnext_finapi** |
|---|---|---|
| Aggregator | Klarna Kosma + EBICS | **finAPI Access V2** |
| Credentials | ALYF holds the licence, you rent | **BYO** — your own finAPI mandator |
| Hosting | SaaS proxy (`banking.alyf.de`) required | **self-hosted**, direct to finAPI |
| Recurring cost | ALYF subscription per account/month | only your finAPI contract (**sandbox free**) |
| Reconciliation | own tool (free) | **native** ERPNext (+ optionally ALYF's free tool) |
| Licence | GPL-3.0 | GPL-3.0 |

> **Honest note:** finAPI/PSD2 connections require fresh **SCA consent every 90 days**. ALYF's EBICS path does not. For pure corporate always-on use, EBICS is technically nicer. We use finAPI because it's a clean BYO-contract path and an open, self-hosted alternative. EBICS may be added as a second provider later (see roadmap).

## Features

- 🔌 **Bank connection import with SCA** — chipTAN / Strong Customer Authentication
  - **Direct multi-step** (`510` challenge–response driven by a Desk wizard) — *works*
  - **WebForm 2.0** (finAPI-hosted, PIN/TAN never touches your server) — *planned*
- 🔄 **Scheduled transaction sync** → native `Bank Transaction` (deduplicated), 4×/day
  - **two-stage**: it makes finAPI fetch from your bank first, then reads — a read-only sync
    silently freezes on the snapshot taken at import time
- 🏦 Maps finAPI accounts to native ERPNext **Bank Account** (by IBAN or by hand)
- 🔎 **Discovers connections** your finAPI user already has — no second SCA consent
- ⏰ **90-day consent watchdog** — warns before PSD2 consent lapses instead of failing silently
- 🔐 Credentials in **encrypted** DocType fields (never in the repo, never in `.env`)
- 🧭 Own **Desk app tile + workspace** (`/app/finapi`), visible to System Manager / Accounts Manager
- 🧪 **Sandbox-first** — develop and test without a live finAPI contract
- ♻️ Reuses ERPNext-native **Bank Reconciliation Tool**
- 🧮 Hands every new batch to ERPNext's own **Bank Transaction Rules** (v16+) right after the sync,
  like the built-in statement import does — the rules only classify, a person still confirms

## Requirements

- [Frappe](https://github.com/frappe/frappe) v15+ — **developed and tested on v16**
- [ERPNext](https://github.com/frappe/erpnext) v15+ — **developed and tested on v16** (provides `Bank`, `Bank Account`, `Bank Transaction`, Bank Reconciliation Tool)
- A finAPI Access account — [sandbox is free](https://finapi.io/), live needs a contract

## Installation

```bash
# In your bench directory
bench get-app https://github.com/clicktrend/erpnext_finapi
bench --site your-site.local install-app erpnext_finapi
bench --site your-site.local migrate
```

## Quickstart (sandbox)

1. Create a free finAPI **sandbox** account and register a *data* client and an *admin* client.
2. In ERPNext open **finAPI Settings**, set `Environment = Sandbox`, paste both client id/secret pairs, click **Test Connection**.
3. Create a **finAPI User** for your Company (registers a finAPI user via the data client).
4. Open **finAPI Bank Connection → New**, **Search Bank**, save, run **Import Connection (SCA)**.
   *(Already have connections at finAPI? Use **Discover Bank Connections** on the finAPI User instead.)*
5. Point each finAPI account in the connection's account table at an ERPNext **Bank Account**.
6. Run **Sync Now** (or enable the scheduler) → transactions appear as native **Bank Transaction**s.
7. Open the native **Bank Reconciliation Tool** and match them.

See the [Wiki](wiki/Home.md) for the full setup, configuration, and architecture.

## Documentation

- 📖 [Wiki Home](wiki/Home.md) · [Installation](wiki/Installation.md) · [Configuration](wiki/Configuration.md)
- 🏦 [finAPI account setup](wiki/finAPI-Account-Setup.md) · [SCA flows](wiki/SCA-Flows.md)
- 🏗️ [Architecture](wiki/Architecture.md) · 🗺️ [Roadmap](ROADMAP.md) · 🤝 [Contributing](CONTRIBUTING.md)

## Licence

[GPL-3.0-or-later](LICENSE). Reusing ERPNext (GPL-3.0) and compatible with ALYF's free reconciliation tool.

## Disclaimer

This project is **not affiliated with, endorsed by, or supported by finAPI GmbH**. "finAPI" is a trademark of its respective owner. Use of the finAPI API is subject to your own agreement with finAPI. Handling bank credentials and PSD2 data carries legal and security responsibility — review before any production use.

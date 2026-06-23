# erpnext_finapi Wiki

Self-hosted **finAPI** bank-account integration for ERPNext — bring your own finAPI contract,
sync transactions, reconcile with ERPNext's native tools.

> These pages seed the GitHub Wiki. Edit them here and sync, or copy into the repository's Wiki.

## Pages

- **[Installation](Installation)** — install into a bench and a site
- **[Configuration](Configuration)** — finAPI Settings, finAPI User, environments
- **[finAPI Account Setup](finAPI-Account-Setup)** — create clients, sandbox vs live, the V1→V2 switch
- **[SCA Flows](SCA-Flows)** — the chipTAN / Strong Customer Authentication state machines
- **[Architecture](Architecture)** — how the feed maps onto native ERPNext accounting
- **[Roadmap](Roadmap)** — phased plan

## In one picture

```
 finAPI Access ──▶  erpnext_finapi  ──▶  Bank Transaction  ──▶  Bank Reconciliation Tool
  (your contract)    (this app)          (native ERPNext)        (native ERPNext)
                                                                  → Payment Entry → clears Invoice
```

`erpnext_finapi` is **only the finAPI feed**. Everything from `Bank Transaction` onward —
matching, reconciliation, payment entries — is **native ERPNext** and intentionally not
re-implemented here. Think of it as *"the ERPNext Plaid integration, but with finAPI"*, built
for the German/EU market.

## Where it fits (and where it doesn't)

finAPI reads what happened on your bank account (Account Information Service). It belongs to
ERPNext's **Bank Transaction + Bank Reconciliation** surface — **not** the Payment Gateway
(`payments` app), which is for letting customers pay you online. See [Architecture](Architecture).

## Status

Alpha / work in progress. The data model, core API client and docs are in place; the SCA import
and scheduled sync are being built against the finAPI sandbox. See [Roadmap](Roadmap).

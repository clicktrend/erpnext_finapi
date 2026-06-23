# Roadmap

The canonical, always-current roadmap lives in [`ROADMAP.md`](../ROADMAP.md) at the repo root.

In short:

1. **Foundation & connection (sandbox)** — app skeleton ✅, data model ✅, `FinApiClient` ✅,
   Test Connection 🚧, direct multi-step SCA import 🚧
2. **Sync & reconciliation** — scheduler → native `Bank Transaction`, 90-day consent handling
3. **WebForm 2.0 & live** — hosted SCA, live mandator
4. **Release & polish** — tests, CI, marketplace listing, translations
5. **Optional** — EBICS as a second provider, Payment Initiation (PIS)

See [SCA Flows](SCA-Flows) for the import state machines and [Architecture](Architecture) for how
the feed maps onto native ERPNext.

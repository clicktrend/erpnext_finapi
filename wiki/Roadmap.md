# Roadmap

The canonical, always-current roadmap lives in [`ROADMAP.md`](../ROADMAP.md) at the repo root.

In short:

1. **Foundation & connection** ✅ — data model, `FinApiClient`, Test Connection, bank search,
   direct multi-step SCA import, account mapping, connection discovery
2. **Sync & reconciliation** ✅ — two-stage sync → native `Bank Transaction` (deduplicated),
   Sync Log, manual sync, 90-day consent watchdog and re-consent flow, ERPNext's own Bank
   Transaction Rules queued after every run that created rows (v16+)
3. **WebForm 2.0 & live** — hosted SCA (blocked on finAPI enabling the product); the read path
   is already live-verified against a production mandator
4. **Release & polish** — unit tests ✅ and CI ✅; marketplace listing and translations open.
   The public release is gated on WebForm 2.0
5. **Optional** — EBICS as a second provider, Payment Initiation (PIS)

See [SCA Flows](SCA-Flows) for the import state machines and [Architecture](Architecture) for how
the feed maps onto native ERPNext.

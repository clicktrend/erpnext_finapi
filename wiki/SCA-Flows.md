# SCA Flows

German banks are PSD2-regulated and require **Strong Customer Authentication** (chipTAN / TAN)
to add a bank connection. finAPI offers two ways to do this. Both are encoded in
`erpnext_finapi/finapi/client.py`.

## A. WebForm 2.0 (finAPI-hosted) — recommended

finAPI hosts the entire SCA page; PIN/TAN never touches your server.

```
create_import_webform(bank_id) ──▶ { id, url, status }
        │
        ▼  user is redirected to  webform-(sandbox|live).finapi.io/...   (valid ~20 min)
   user completes TAN on finAPI's page
        │
        ▼  finAPI redirects back to your Redirect URL (allow_guest callback)
   poll get_webform_status(id) until COMPLETED → import accounts
```

Statuses: `NOT_YET_OPENED → IN_PROGRESS → COMPLETED | COMPLETED_WITH_ERROR | ABORTED | EXPIRED`.

**Gate:** requires the WebForm 2.0 product to be enabled for your mandator (otherwise `403`).
See [finAPI Account Setup](finAPI-Account-Setup#5-webform-20-enablement-live).

## B. Direct multi-step (licensed) — works today

You drive the SCA yourself. finAPI signals "another step needed" with HTTP **`510`**
(`ADDITIONAL_AUTHENTICATION_REQUIRED`). **This is not an error** — it's the expected flow. The
client raises `ScaChallengeRequired`, carrying the stateful `multiStepAuthentication` object.

```
import_bank_connection(bank_id, login_credentials=[...])
        │
        ▼  510  multiStepAuthentication.status = TWO_STEP_PROCEDURE_REQUIRED
   user picks a TAN scheme from twoStepProcedures[]
        │
        ▼  import_bank_connection(..., multi_step={ hash, twoStepProcedureId })
        │
        ▼  510  multiStepAuthentication.status = CHALLENGE_RESPONSE_REQUIRED  (+ challengeMessage)
   user enters the TAN
        │
        ▼  import_bank_connection(..., multi_step={ hash, twoStepProcedureId, challengeResponse })
        │
        ▼  201  bank connection created
```

### Rules

- ⚠️ **finAPI nests `multiStepAuthentication` inside `errors[0]`**, not at the top level of the
  510 body. Reading only the top level turns every SCA step into an unexplained error. The client
  reads `errors[0]` first and tolerates a top-level variant.
- **The full body — including `loginCredentials` — is re-sent on every step**, alongside the
  `multiStepAuthentication` object. The `hash` ties the steps together.
- **Keep PIN/TAN server-side and transient.** `sca.py` holds the in-flight state in the Frappe
  cache under a 15-minute TTL, keyed by the bank connection, and clears it on success, cancel and
  failure alike. It is never returned to the browser and never written to the database.
- **`storeSecrets: true`** is sent on import so finAPI can later refresh the connection unattended.
  Without it the scheduled sync can never run stage one.
- Interface: usually `XS2A`; `FINTS_SERVER` is also possible. Test both for a given bank.

### In the Desk

`finAPI Bank Connection` drives the whole flow: **Search Bank** → **Import Connection (SCA)** →
credential dialog (built from the labels the bank declares) → TAN scheme → TAN → done, accounts
mapped. `TWO_STEP_PROCEDURE_REQUIRED`, `CHALLENGE_RESPONSE_REQUIRED`, `REDIRECT_REQUIRED` and
`DECOUPLED_AUTH_REQUIRED` are all handled.

## C. Re-consent (the 90-day wall)

PSD2 consent expires — typically after 90 days, and finAPI reports the exact date in
`interfaces[].aisConsent.expiresAt`. When it lapses the sync stops delivering new transactions
**silently**, which is why a daily task warns ahead of time (`consent_warning_days`) and flags the
connection `Update Required`.

Renewal is **Update Connection**: the same multi-step machine against
`POST /bankConnections/update`.

> ⚠️ The update endpoint's field is **`bankingInterface`**, exactly like the import. finAPI's prose
> docs say `interface`; sending that makes finAPI reject the entire body with "request contains no
> data / invalid JSON" — a 400 that looks like an encoding bug and is not one.

## D. Adopting a connection that already exists

If the finAPI user already owns connections (created by a previous system or through finAPI's
hosted web form), **do not re-import** — that would force a second consent. Use **Discover Bank
Connections** on the `finAPI User`: it reads them and creates the matching records, accounts
included.

## Why the app ships B first

The direct path works with a standard licensed mandator and the free sandbox, so the MVP targets
it. WebForm 2.0 is wired in afterwards, once finAPI enables it for the live mandator.

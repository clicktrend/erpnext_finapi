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

- **The full body — including `loginCredentials` — is re-sent on every step**, alongside the
  `multiStepAuthentication` object. The `hash` ties the steps together.
- **Keep PIN/TAN server-side and transient.** Store the in-flight state in the bank connection
  doc or a short-lived cache key, **never in the browser**, and clear it the moment the flow ends
  (success or abort). This is PSD2-sensitive — review before production.
- Interface: usually `XS2A`; `FINTS_SERVER` is also possible. Test both for a given bank.

## Why the app ships B first

The direct path works with a standard licensed mandator and the free sandbox, so the MVP targets
it. WebForm 2.0 is wired in afterwards, once finAPI enables it for the live mandator.

# Configuration

## 1. finAPI Settings (single)

Go to **finAPI Settings**. All credentials are stored in **encrypted** password fields — never
in `.env`, never in the repo.

| Field | Meaning |
|---|---|
| **Environment** | `Sandbox` (free, for dev) or `Live`. The API & WebForm hosts are derived automatically. |
| **API Version** | `V2` (read-only). Your finAPI mandator must be scoped to V2 — see [finAPI Account Setup](finAPI-Account-Setup). |
| **API Host / WebForm Host** | Read-only, derived from Environment (`sandbox` / `live`, `webform-sandbox` / `webform-live`). |
| **Data Client ID / Secret** | The finAPI **data** client — creates users, searches banks, runs webforms. |
| **Admin Client ID / Secret** | Optional. The **admin** client — `mandatorAdmin` calls and the V1→V2 switch only. |
| **Redirect URL** | WebForm 2.0 callback URL (must be whitelisted in the finAPI portal). |

Click **Test Connection** to verify the data client credentials. The result is shown under
*Last Connection Test*.

> ⚠️ **Two clients, two roles.** Using the admin client for data operations (or vice versa)
> returns `403`. The app keeps them separate; just paste each pair into its own field.

## 2. finAPI User

One **finAPI User** per ERPNext Company (and per environment — sandbox and live are separate
user pools).

- Set a **finAPI Username** (the finAPI user id/login) and optionally a password.
- Use the **Register** action to create the user at finAPI (`POST /api/v2/users` via the data
  client). The returned finAPI user id and any generated password are stored back.

This user owns the bank connections and is used for the password-grant **user token**.

## 3. Bank Connection

Create a **finAPI Bank Connection**, pick the finAPI User, and run the import (SCA) flow —
see [SCA Flows](SCA-Flows). On success, the connection's `Accounts` table is populated; map each
finAPI account to a native ERPNext **Bank Account**.

## 4. Sync

The scheduled task `erpnext_finapi.tasks.sync_all_bank_connections` (daily) pulls new
transactions into native `Bank Transaction` records. A **finAPI Sync Log** records each run.

> PSD2 consent typically expires after **90 days** — watch `SCA Consent Expiry` on the connection
> and re-authenticate before it lapses, or the sync stops silently.

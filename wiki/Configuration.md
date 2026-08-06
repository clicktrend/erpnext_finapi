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
| **Enable Scheduled Sync** | Master switch for the 4×/day sync. Leave it off until your accounts are linked. |
| **Initial Sync (days)** | How far back the very first sync of a connection reads (default 90). |
| **Sync Overlap (days)** | Safety overlap re-read on every run (default 2). Duplicates are filtered by finAPI transaction id. |
| **Consent Warning (days)** | How early to warn before the PSD2 consent expires (default 14). |

Click **Test Connection** to verify the data client credentials. The result is shown under
*Last Connection Test*.

> ⚠️ **Two clients, two roles.** Using the admin client for data operations (or vice versa)
> returns `403`. The app keeps them separate; just paste each pair into its own field.

## 2. finAPI User

One **finAPI User** per ERPNext Company (and per environment — sandbox and live are separate
user pools).

- Set a **finAPI Username** (the finAPI user id/login) and optionally a password.
- Use the **Register at finAPI** action to create the user at finAPI (`POST /api/v2/users` via the
  data client). The returned finAPI user id and any generated password are stored back.
- **Already have a finAPI user?** Enter its username and password, tick *Registered*, and skip
  registration — re-creating it would fail.

This user owns the bank connections and is used for the password-grant **user token**.

## 3. Bank Connection

**Already have connections at finAPI?** Run **Discover Bank Connections** on the finAPI User. It
adopts them (with their accounts) instead of forcing a second SCA consent.

Otherwise create a **finAPI Bank Connection**, pick the finAPI User, **Search Bank**, save, and run
**Import Connection (SCA)** — see [SCA Flows](SCA-Flows).

Either way the connection's `Accounts` table is then populated. Each finAPI account must point at a
native ERPNext **Bank Account**:

- accounts are matched **by IBAN** automatically;
- if your Bank Accounts have no IBAN stored (common), pick the Bank Account by hand in the table —
  the finAPI account id is mirrored onto `Bank Account.integration_id` either way.

**Accounts without a Bank Account are skipped by the sync** — that is the deliberate safety valve,
not an error.

## 4. Sync

- **Scheduled:** `erpnext_finapi.tasks.sync_all_bank_connections` runs **4×/day** (`0 7,11,15,19`)
  for every connection with *Include in Scheduled Sync*, provided *Enable Scheduled Sync* is on.
- **Manual:** **Sync Now** on the connection (queued in the background).
- Each run writes a **finAPI Sync Log** (fetched / created / status / error).

> The cadence is a PSD2 constraint: **unattended bank updates are capped at 4 per 24h** per
> connection. Do not schedule it more often.

### Consent

PSD2 consent typically expires after **90 days** (`SCA Consent Expiry` on the connection; finAPI's
own value is used when it reports one). A daily task warns the Accounts Managers beforehand and
flags an expired connection as `Update Required`. Renew with **Update Connection** — otherwise the
sync stops delivering new transactions **silently**.

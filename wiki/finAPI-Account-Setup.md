# finAPI Account Setup

`erpnext_finapi` is **bring-your-own-contract**: you use your own finAPI mandator. finAPI's
**sandbox is free**, so you can develop and test the whole flow without a paid agreement.

## 1. Create a finAPI account

Sign up at [finapi.io](https://finapi.io/). You get a **mandator** with two registered
OAuth clients (a *data* client and an *admin* client).

## 2. The two clients (important)

| Client | Can do | Cannot do |
|---|---|---|
| **Data client** | create users (`POST /api/v2/users`), user tokens (password grant), bank search, webforms | mandatorAdmin calls |
| **Admin client** | `/api/v2/mandatorAdmin/*`, the V1→V2 version switch | create users, search banks |

Using the wrong client for an operation returns **`403`**. Put each pair into the matching field
in [finAPI Settings](Configuration).

## 3. Hosts

| Environment | API host | WebForm host |
|---|---|---|
| Sandbox | `https://sandbox.finapi.io` | `https://webform-sandbox.finapi.io` |
| Live | `https://live.finapi.io` | `https://webform-live.finapi.io` |

> ⚠️ **`webform.finapi.io` does not exist** (DNS fails). Only the `-sandbox` / `-live` variants are
> valid. The app knows both hosts as constants and picks the one belonging to the finAPI User's
> environment, so you never type a host by hand — and Sandbox and Live can be configured at the
> same time (one credential section each).

## 4. Mandator API version (V1 → V2)

A mandator is **scoped to one API version**. A V1-scoped mandator calling `/api/v2/*` gets:

```
403  "client is limited to scope /api/v1"
```

Switch it to V2 with the **admin** client:

```
POST {host}/api/v1/mandatorAdmin/switchApiVersion
{ "apiVersion": "V2" }
```

- The body field is **`apiVersion`** (not `targetVersion`, which returns `BAD_REQUEST`).
- The switch is **reversible for 7 days**, then permanent. Don't build hard dependencies during
  the rollback window.

## 5. WebForm 2.0 enablement (live)

The hosted WebForm 2.0 import (`POST /api/webForms/bankConnectionImport`) is a separate finAPI
product. On a live mandator that hasn't been enabled for it, finAPI returns **`403 "Access Denied"`** —
contact finAPI support to activate it. Until then, use the **direct multi-step** SCA path, which
works with a standard licensed mandator. See [SCA Flows](SCA-Flows).

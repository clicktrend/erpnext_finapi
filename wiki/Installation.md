# Installation

## Requirements

- [Frappe](https://github.com/frappe/frappe) **v15+**
- [ERPNext](https://github.com/frappe/erpnext) **v15+** — provides `Bank`, `Bank Account`,
  `Bank Transaction` and the Bank Reconciliation Tool that this app feeds
- A finAPI Access account ([sandbox is free](https://finapi.io/))

## Install into a bench + site

```bash
# 1. Fetch the app into your bench's apps/ directory (git clone under the hood)
bench get-app https://github.com/clicktrend/erpnext_finapi

# 2. Install it into a site (runs migrations, creates the DocTypes)
bench --site your-site.local install-app erpnext_finapi

# 3. (after pulling updates)
bench --site your-site.local migrate
```

## How it lives in a bench

A Frappe app only runs when it physically sits in `frappe-bench/apps/<app>/` and is registered
in the bench. `bench get-app` does both: it **git-clones** the repo into `apps/` and pip-installs
it (editable) so `apps.txt` knows about it.

> **The bench is disposable; your git remote is the source of truth.** `frappe-bench/` is created
> per machine by `bench init` and is not version-controlled. If it is wiped, you re-create it and
> `bench get-app` clones this app back from its remote. **Always keep the git remote up to date** —
> anything committed only inside the bench and never pushed is lost when the bench is recreated.

## Developer setup

```bash
bench get-app /path/to/erpnext_finapi      # or your fork's URL
bench --site dev.local install-app erpnext_finapi
bench --site dev.local migrate

# Enable developer mode so DocType changes are written back to JSON
bench --site dev.local set-config developer_mode 1
bench --site dev.local clear-cache
```

Then open **finAPI Settings** and configure the **Sandbox** environment — see
[Configuration](Configuration).

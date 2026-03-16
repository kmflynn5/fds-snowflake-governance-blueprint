<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Greenfield Trial Run — Testing Plan

*Flynn Data Services · Core Stage (Phase 1)*

This document walks through a full end-to-end deployment of the Core stage
against a Snowflake trial account. It doubles as a GET_STARTED guide for any
new greenfield engagement — once you've verified it works here, the only
difference on a client account is the intake answers and the auth credentials.

---

## What This Deploys

Running through this plan will create the following in your Snowflake account:

**Roles (12 total)**
- Functional: `LOADER`, `TRANSFORMER`, `ANALYST`, `FIREFIGHTER`, `AUDITOR`
- Connector: `CONN_FIVETRAN`, `CONN_AIRFLOW`, `CONN_SNOWPIPE_SNOWPLOW`, `CONN_DBT_PROD`, `CONN_LOOKER`
- Object: `OBJ_RAW_FIVETRAN_WRITER`, `OBJ_RAW_AIRFLOW_WRITER`, `OBJ_EVENTS_WRITER`, `OBJ_ANALYTICS_WRITER`, `OBJ_MARTS_READER` (and source readers for dbt)

**Warehouses (3 total, each with resource monitor)**
- `WH_INGEST` + `RM_WH_INGEST`
- `WH_TRANSFORM` + `RM_WH_TRANSFORM`
- `WH_ANALYTICS` + `RM_WH_ANALYTICS`

**Databases and schemas**
- `RAW_FIVETRAN`, `RAW_AIRFLOW`, `EVENTS` (with schema `SNOWPLOW`), `ANALYTICS`, `MARTS`

All derived from `intake/connectors.yaml` via `scripts/generate_tf.py`. To
deploy a different connector topology, edit the YAML and re-run codegen —
never edit the generated `.auto.tfvars.json` or the Terraform modules directly.

---

## Prerequisites

### Tooling

```bash
# Python environment (uv required)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --group dev

# Terraform >= 1.5
brew install terraform   # or https://developer.hashicorp.com/terraform/install

# Verify
uv run python --version   # 3.11+
terraform version          # >= 1.5
```

### Snowflake trial account

Sign up at snowflake.com — the 30-day trial includes $400 in credits, which
is more than enough for this deployment and validation.

Note your **account identifier** — it appears in the URL after login:
`https://<account-identifier>.snowflakecomputing.com`

The format expected by the provider is `<orgname>-<account_name>` (e.g.
`myorg-xy12345`) or the legacy `xy12345.us-east-1` format. Both work.

---

## Step 1 — Create the Terraform Service Account

The provider authenticates as a dedicated service account, not as your personal
admin user. Run these SQL statements in Snowsight as `ACCOUNTADMIN`.

### 1a. Generate a keypair

```bash
# From the repo root
openssl genrsa -out ~/.snowflake/tf_rsa_key.pem 2048
openssl rsa -in ~/.snowflake/tf_rsa_key.pem -pubout -out ~/.snowflake/tf_rsa_key.pub
```

Copy the public key (everything between `-----BEGIN PUBLIC KEY-----` and
`-----END PUBLIC KEY-----`, with no line breaks):

```bash
grep -v "^-----" ~/.snowflake/tf_rsa_key.pub | tr -d '\n'
```

### 1b. Create the service account in Snowflake

```sql
-- Run as ACCOUNTADMIN in Snowsight
USE ROLE ACCOUNTADMIN;

-- Terraform operates as SYSADMIN for infrastructure work
CREATE ROLE IF NOT EXISTS TF_SYSADMIN
  COMMENT = 'Terraform automation role — infrastructure apply only';

GRANT ROLE SYSADMIN TO ROLE TF_SYSADMIN;

CREATE USER IF NOT EXISTS TF_SYSADMIN
  DEFAULT_ROLE     = TF_SYSADMIN
  DEFAULT_WAREHOUSE = NULL
  RSA_PUBLIC_KEY   = '<paste_public_key_here>'
  COMMENT          = 'Terraform service account — key-pair auth only, no password';

GRANT ROLE TF_SYSADMIN TO USER TF_SYSADMIN;
```

> **Why TF_SYSADMIN and not ACCOUNTADMIN?**
> Terraform only needs to create roles, databases, warehouses, and grants —
> all of which are within SYSADMIN's scope. ACCOUNTADMIN is reserved for
> account-level administration and should have zero active session assignments
> in any environment. See `docs/PHILOSOPHY.md §Core Principles #4`.

---

## Step 2 — Configure Environment Variables

The provider reads auth from env vars automatically — no HCL configuration
needed. Create a `.env` file in `terraform/` and source it before running
Terraform (`.env` is gitignored):

```bash
SNOWFLAKE_ORGANIZATION_NAME="<org-name>"       # e.g. MYORG (before the dash)
SNOWFLAKE_ACCOUNT_NAME="<account-name>"        # e.g. XY12345 (after the dash)
SNOWFLAKE_USER="TF_SYSADMIN"
SNOWFLAKE_PRIVATE_KEY_PATH="$HOME/.snowflake/tf_rsa_key.pem"
SNOWFLAKE_ROLE="TF_SYSADMIN"
SNOWFLAKE_AUTHENTICATOR="SNOWFLAKE_JWT"
```

Your account identifier appears in the Snowsight URL:
`https://<org-name>-<account-name>.snowflakecomputing.com`

Source the file and verify the connection before proceeding:

```bash
set -a; source .env; set +a

snow connection add -n tf_sysadmin -u TF_SYSADMIN -r TF_SYSADMIN \
  -k ~/.snowflake/tf_rsa_key.pem -a <org-name>-<account-name>
# authenticator: SNOWFLAKE_JWT

snow connection test -c tf_sysadmin
# Expected: Status OK, Role: TF_SYSADMIN
```

---

## Step 3 — Review and Customize the Intake Config

The example `intake/connectors.yaml` already defines the five connectors from
`docs/SPEC.md §1.2` (Fivetran, Airflow, Snowpipe, dbt, Looker). For this
trial run you can use it as-is.

If you want to customize for a real client, edit `intake/connectors.yaml`
following the schema in `docs/SPEC.md §1.2`. Common changes:

- Remove connectors that don't apply (`SNOWPIPE_SNOWPLOW`, `LOOKER`, etc.)
- Change database names to match the client's naming convention
- Adjust warehouse sizes (`size: XSMALL` → `SMALL` / `MEDIUM`)
- Set real credit quotas (`monthly_credit_quota: 100`)

Also review `intake/tags.yaml` — tags are collected at Core but not enforced
until the Observability expansion. No changes needed for the trial.

---

## Step 4 — Run Codegen

```bash
uv run scripts/generate_tf.py
```

This reads `intake/connectors.yaml` and writes three files to
`terraform/`:

```
terraform/
  databases.auto.tfvars.json    # databases + schemas
  warehouses.auto.tfvars.json   # warehouses with sizes + resource monitor config
  rbac.auto.tfvars.json         # roles, object roles, grant mappings
```

Spot-check the output before applying:

```bash
# Warehouses — should match connectors.yaml warehouse fields
python -m json.tool terraform/warehouses.auto.tfvars.json

# RBAC — verify connector roles and object role mappings
python -m json.tool terraform/rbac.auto.tfvars.json | head -80
```

Run unit tests to confirm no regressions in codegen logic:

```bash
uv run pytest tests/unit/ -q
# Expected: 52 passed
```

---

## Step 5 — Configure terraform.tfvars

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
```

Edit `terraform/terraform.tfvars` — the only required change for the trial
is the notify user:

```hcl
environment = "prod"

# Replace ADMIN with your actual Snowflake username
resource_monitor_notify_users = ["<your-snowflake-username>"]
```

`terraform.tfvars` is gitignored — never commit it.

---

## Step 6 — Initialize and Validate

```bash
cd terraform

terraform init -backend=false
# Expected: "Terraform has been successfully initialized!"
# Provider: snowflakedb/snowflake 0.100.x

terraform validate
# Expected: "Success! The configuration is valid."

terraform fmt -check
# Expected: no output (already formatted)
```

---

## Step 7 — Plan

```bash
terraform plan -out=trial.tfplan
```

Review the plan output. Expected resource counts for the default
`connectors.yaml`:

| Resource type | Count |
|---|---|
| `snowflake_account_role` | ~12 roles |
| `snowflake_warehouse` | 3 |
| `snowflake_resource_monitor` | 3 |
| `snowflake_database` | 5 |
| `snowflake_schema` | 1+ |
| `snowflake_grant_privileges_to_account_role` | ~20+ |
| `snowflake_grant_account_role` | ~10+ |

If you see unexpected destroys or replacements, stop and investigate before
applying. A clean plan should show only `add` operations on a fresh account.

---

## Step 8 — Apply

```bash
terraform apply trial.tfplan
```

Apply takes 2–4 minutes for the default connector set. Snowflake API calls
are not parallelizable beyond what the provider manages internally.

If any resource fails:
1. Note the error message — do not re-run apply blindly
2. Check if the resource was partially created in Snowsight (Roles, Warehouses,
   Data → Databases menus)
3. Fix the underlying issue, then re-run `terraform plan` to confirm the delta
   before re-applying

---

## Step 9 — Verify in Snowsight

Log in to Snowsight as your personal admin user (not TF_SYSADMIN) and
verify the following:

### Roles
**Admin → Roles**

- [ ] `CONN_FIVETRAN`, `CONN_AIRFLOW`, `CONN_SNOWPIPE_SNOWPLOW`, `CONN_DBT_PROD`, `CONN_LOOKER` exist
- [ ] `OBJ_RAW_FIVETRAN_WRITER` (and other OBJ_ roles) exist
- [ ] `LOADER`, `TRANSFORMER`, `ANALYST` exist
- [ ] `FIREFIGHTER` exists with no users assigned
- [ ] `AUDITOR` exists

### Warehouses
**Admin → Warehouses**

- [ ] `WH_INGEST`, `WH_TRANSFORM`, `WH_ANALYTICS` exist with size `XSMALL`
- [ ] Each shows a resource monitor (`RM_WH_INGEST`, etc.) in the details panel

### Databases
**Data → Databases**

- [ ] `RAW_FIVETRAN`, `RAW_AIRFLOW`, `EVENTS`, `ANALYTICS`, `MARTS` exist
- [ ] `EVENTS` has a schema `SNOWPLOW`

### Privilege spot-checks (run as ACCOUNTADMIN)

```sql
-- Confirm CONN_FIVETRAN inherits OBJ_RAW_FIVETRAN_WRITER
SHOW GRANTS TO ROLE CONN_FIVETRAN;

-- Confirm FIREFIGHTER has no user assignments
SHOW GRANTS OF ROLE FIREFIGHTER;
-- Expected: empty

-- Confirm resource monitor is attached to WH_INGEST
SHOW WAREHOUSES LIKE 'WH_INGEST';
-- Check the resource_monitor column

-- Confirm dbt can see source databases (should have USAGE)
SHOW GRANTS TO ROLE CONN_DBT_PROD;
```

---

## Step 10 — Terraform State Check

Confirm Terraform agrees with the live state (no drift):

```bash
# From terraform/ directory
terraform plan -detailed-exitcode
# Exit code 0 = no changes needed — state matches live environment
```

---

## Teardown

When done with the trial, destroy all managed resources:

```bash
cd terraform
terraform destroy
```

Then drop the service account manually (Terraform doesn't manage its own
service account):

```sql
-- Run as ACCOUNTADMIN
DROP USER IF EXISTS TF_SYSADMIN;
DROP ROLE IF EXISTS TF_SYSADMIN;
```

---

## Known Limitations (Core Stage)

The following are intentionally deferred to expansion packs and are **not**
part of this trial:

| Item | Expansion | Notes |
|---|---|---|
| Tag enforcement policy | Observability | `tags.yaml` is committed; tagging module not yet built |
| Eval suite (RBAC assertions) | Observability | `tests/eval/` not yet implemented |
| CI/CD terraform plan gate | Observability | `.github/workflows/terraform-plan.yml` not yet built |
| FIREFIGHTER activation alerting | Enforcement | Manual check only at this stage |
| Cost anomaly detection | Observability | Resource monitors alert on budget, not on anomalies |

For a Core-stage engagement, the manual Snowsight checks in Step 9 are the
verification layer. The eval suite (Observability expansion) is what automates
and schedules those checks.

---

## Adapting for a Real Client Engagement

The only files that change per-client are in `intake/`:

```
intake/connectors.yaml    # their integrations, databases, warehouses
intake/tags.yaml          # their cost centers and classification taxonomy
intake/decisions.md       # their design decisions with rationale
```

Workflow for a new client:
1. Fork or clone this repo into a client-specific repo
2. Complete `docs/greenfield_intake.md` with the client (or run `/intake-greenfield` skill)
3. Edit `intake/connectors.yaml` and `intake/tags.yaml` with the intake answers
4. Run `uv run scripts/generate_tf.py`
5. Follow Steps 5–9 above against the client account
6. Commit the generated `.auto.tfvars.json` files — they are the reviewable
   artifact that documents exactly what was deployed and why

The Terraform modules are never edited per-client. All customization flows
through YAML.

---

*Flynn Data Services · flynndata.com · Last reviewed: March 2026*

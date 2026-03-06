# Snowflake Governance Framework — Project Spec
*Flynn Data Services · References: PHILOSOPHY.md, greenfield_intake.md,
brownfield_intake.md*

---

## Purpose

This spec defines the build plan for the Flynn Data Services Snowflake
Governance Framework — a "Golden Path" repository that demonstrates a
high-maturity Snowflake environment using Terraform.

The repo serves three purposes:
1. A working reference for client engagements — forkable, adaptable, and
   grounded in real delivery patterns
2. A publishable artifact (GitHub + blog post) that demonstrates governance
   philosophy in practice
3. A foundation for the intake-to-deployment workflow: intake docs produce
   config, config drives Terraform, Terraform is verified by the eval suite

**Every design decision in this repo is traceable to PHILOSOPHY.md.** If a
decision cannot be traced there, either the spec is wrong or PHILOSOPHY.md
needs to be updated first.

---

## How This Repo Gets Used

The intake process is the entry point — not the Terraform.

```
Client engagement starts
        │
        ▼
┌───────────────────┐
│  Intake Process   │
│                   │
│  Greenfield?      │  greenfield_intake.md
│  → Interview      │  produces connectors.yaml
│                   │  + decisions.md
│  Brownfield?      │  brownfield_intake.md
│  → Survey first   │  survey output + interview
│  → Then interview │  produces connectors.yaml
│                   │  + decisions.md
│                   │  + migration_plan.md
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Config Layer     │
│                   │
│  connectors.yaml  │  ← drives RBAC + warehouse Terraform
│  tags.yaml        │  ← drives tagging module
│  decisions.md     │  ← audit trail, not consumed by Terraform
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Terraform        │
│                   │
│  Reads config     │
│  Generates roles, │
│  warehouses,      │
│  grants, tags     │
└────────┬──────────┘
         │
         ▼
┌───────────────────┐
│  Eval Suite       │
│                   │
│  Verifies live    │
│  environment      │
│  matches declared │
│  config           │
└───────────────────┘
```

---

## Repo Structure

```
/
├── PHILOSOPHY.md                    # Governance standard — read first
│
├── intake/
│   ├── greenfield_intake.md         # Intake questionnaire — greenfield
│   ├── brownfield_intake.md         # Environment survey + interview — brownfield
│   ├── connectors.yaml              # Generated output — drives Terraform RBAC
│   ├── tags.yaml                    # Generated output — drives Terraform tagging
│   └── decisions.md                 # Generated output — audit trail
│
├── terraform/
│   ├── main.tf                      # Root module — wires everything together
│   ├── variables.tf
│   ├── outputs.tf
│   └── modules/
│       ├── rbac/                    # Role hierarchy, connector roles, grants
│       │   ├── main.tf
│       │   ├── connectors.tf        # for_each over connectors.yaml
│       │   ├── functional_roles.tf  # LOADER, TRANSFORMER, ANALYST, FIREFIGHTER
│       │   ├── object_roles.tf      # OBJ_{DB}_{SCOPE}_{PRIVILEGE} pattern
│       │   └── variables.tf
│       ├── warehouses/              # Workload-separated warehouses + monitors
│       │   ├── main.tf
│       │   ├── resource_monitors.tf
│       │   └── variables.tf
│       ├── databases/               # Database + schema structure
│       │   ├── main.tf
│       │   └── variables.tf
│       └── tags/                    # Tag taxonomy + object tag policies
│           ├── main.tf
│           ├── policies.tf          # Enforcement policies (Walk/Run stage)
│           └── variables.tf
│
├── scripts/
│   ├── tagging/
│   │   └── backfill_tags.py         # Backfill tags on existing objects
│   └── user_onboarding/
│       └── provision_service_account.py
│
├── tests/
│   ├── eval/
│   │   ├── conftest.py              # Snowflake fixtures via AUDITOR role
│   │   ├── test_rbac.py             # Privilege boundary assertions
│   │   ├── test_breakglass.py       # FIREFIGHTER activity assertions
│   │   ├── test_tagging.py          # Tag completeness assertions
│   │   └── test_cost.py             # Resource monitor + query anomaly assertions
│   └── unit/
│       └── test_mocks.py            # Local tests with mocked Snowflake connections
│
├── runbooks/
│   └── migration.md                 # Brownfield migration decision tree
│
├── .github/
│   └── workflows/
│       └── terraform-plan.yml       # PR gate: terraform plan on RBAC changes
│
└── Makefile                         # Local lint, test, and plan shortcuts
```

---

## Part 1 — Intake & Config Layer

### 1.1 The Intake Process

Before any Terraform is written, the intake process is completed. See:
- `intake/greenfield_intake.md` for new environments
- `intake/brownfield_intake.md` for existing environments

The intake produces three files that live in `/intake/` and are committed
to the repo:

**`connectors.yaml`** — the primary config file. Defines every ingestion
integration, its target database/schema, required privileges, and assigned
warehouse. Consumed by `terraform/modules/rbac/connectors.tf` via `for_each`.

**`tags.yaml`** — defines the tag taxonomy for this environment. Consumed by
`terraform/modules/tags/`.

**`decisions.md`** — documents every governance design decision made during
intake, with rationale and reference to PHILOSOPHY.md. Not consumed by
Terraform. Exists as an audit trail and onboarding document.

### 1.2 connectors.yaml Schema

```yaml
# intake/connectors.yaml
# Generated during intake. Each entry produces:
#   - A CONN_{name} account role
#   - An OBJ_{target_db}_{scope}_{privilege_tier} object role
#   - The appropriate privilege grants
#   - Assignment to WH_{warehouse}

connectors:
  - name: FIVETRAN                   # becomes CONN_FIVETRAN
    type: etl                        # etl | orchestrator | event_stream | custom
    target_db: RAW_FIVETRAN          # isolated database per PHILOSOPHY.md
    target_schemas: ["*"]            # all schemas in this db, or list specific
    privileges: [INSERT, CREATE TABLE]
    warehouse: INGEST                # becomes WH_INGEST
    reason: "Fivetran managed ETL — writes source replicas to isolated RAW db"
    vendor_managed: true             # Fivetran manages the credential

  - name: AIRFLOW
    type: orchestrator
    target_db: RAW_AIRFLOW
    target_schemas: ["*"]
    privileges: [INSERT, CREATE TABLE, SELECT]  # needs read-back for incremental
    warehouse: INGEST
    reason: "Airflow custom ingestion pipelines — needs SELECT for incremental logic"
    vendor_managed: false

  - name: SNOWPIPE_SNOWPLOW
    type: event_stream
    target_db: EVENTS
    target_schemas: ["SNOWPLOW"]
    privileges: [INSERT, CREATE PIPE, MONITOR]
    extra_grants: [CREATE PIPE]      # Snowpipe-specific — see PHILOSOPHY.md note
    warehouse: INGEST
    reason: "Snowpipe continuous load from S3 — scoped to EVENTS.SNOWPLOW only"
    vendor_managed: false

  - name: DBT_PROD
    type: transformer
    source_dbs: ["RAW_FIVETRAN", "RAW_AIRFLOW", "EVENTS"]  # read access
    target_db: ANALYTICS
    target_schemas: ["*"]
    privileges: [SELECT, INSERT, CREATE TABLE, CREATE SCHEMA]
    warehouse: TRANSFORM
    reason: "dbt production runs — reads all RAW, writes to ANALYTICS"
    vendor_managed: false

  - name: LOOKER
    type: bi_tool
    source_db: MARTS
    target_schemas: ["*"]
    privileges: [SELECT]
    warehouse: ANALYTICS
    reason: "Looker BI tool — read-only access to final MARTS layer"
    vendor_managed: true
```

### 1.3 tags.yaml Schema

```yaml
# intake/tags.yaml
# Generated during intake. Defines the tag taxonomy for this environment.
# Consumed by terraform/modules/tags/.

required_tags:                       # All objects must have these at Walk stage
  - name: cost_center
    values: ["engineering", "analytics", "product", "infrastructure"]
    apply_to: [database, schema, warehouse]

  - name: environment
    values: ["prod", "staging", "dev"]
    apply_to: [database, schema, warehouse]

  - name: owner
    values: []                       # freeform — team or person name
    apply_to: [database, schema]

optional_tags:                       # Recommended but not enforced at Walk stage
  - name: project
    apply_to: [schema, table]

  - name: sensitivity
    values: ["public", "internal", "confidential", "restricted"]
    apply_to: [database, schema, table]

  - name: pii
    values: ["true", "false"]
    apply_to: [table, column]

enforcement_stage: walk              # crawl | walk | run
# crawl: tags defined but not enforced
# walk: required_tags enforced on new objects via tag policy
# run: tag policy blocks object creation if required tags are missing
```

---

## Part 2 — RBAC Hierarchy

*References: PHILOSOPHY.md §Core Principles, §Connector Role Philosophy*

### Role Hierarchy

```
ACCOUNTADMIN                         # zero active users in production
  └── SYSADMIN                       # infrastructure setup only
      └── FIREFIGHTER                # dormant, no assigned users
                                     # activates for emergency intervention only

Functional Roles (conceptual — not directly assigned to users/service accounts)
  LOADER                             # conceptual grouping for ingestion connectors
  TRANSFORMER                        # conceptual grouping for transformation tools
  ANALYST                            # human analysts and BI tool service accounts

Connector Roles (operational — assigned to service accounts)
  CONN_{INTEGRATION}                 # one per integration, generated from connectors.yaml
    └── OBJ_{DB}_{SCOPE}_WRITER/READER
    └── WH_{WORKLOAD}_USAGE

Object Roles (privilege holders — never assigned directly to users)
  OBJ_{DB}_{SCOPE}_WRITER            # write access to specific db/schema
  OBJ_{DB}_{SCOPE}_READER            # read access to specific db/schema

Special Roles
  AUDITOR                            # read-only, used by eval suite only
                                     # access to account_usage views, no data access
```

### Terraform Implementation Notes

- All roles generated via `for_each` over `connectors.yaml` — no hardcoded
  role resources for connector or object roles
- Functional roles are defined as static resources with comments documenting
  their conceptual purpose
- FIREFIGHTER is defined as a static resource with zero grants to users;
  a separate `reconciliation_check` script asserts this daily
- AUDITOR role is defined separately from the connector pattern — it is an
  operational role for the eval suite, not an integration connector

---

## Part 3 — Warehouses & Resource Monitors

*References: PHILOSOPHY.md §Maturity Model — Crawl*

### Default Warehouse Topology

```
WH_INGEST      # all CONN_{ETL/ORCHESTRATOR/EVENT_STREAM} connectors
WH_TRANSFORM   # all CONN_{TRANSFORMER} connectors
WH_ANALYTICS   # all CONN_{BI_TOOL} connectors + ANALYST functional role
```

Additional warehouses defined in `connectors.yaml` if a workload warrants
isolation (e.g. high-volume event pipeline, ML workload).

### Resource Monitor Defaults

Every warehouse gets a resource monitor at Crawl stage. Default thresholds
(override in `connectors.yaml` per warehouse):

| Threshold | Action |
|-----------|--------|
| 75% of monthly credit budget | Notify account admins |
| 100% of monthly credit budget | Suspend warehouse |

Credit budgets are set during intake (greenfield_intake.md Section 5,
brownfield_intake.md Part 2 Section 2.3).

---

## Part 4 — Tagging Taxonomy

*References: PHILOSOPHY.md §Maturity Model — Walk and Run*

Tag taxonomy is defined in `intake/tags.yaml` and consumed by
`terraform/modules/tags/`.

### Enforcement by Maturity Stage

**Crawl:** Tags module is deployed, taxonomy is defined, but no enforcement
policy is active. Tags are applied manually or via `scripts/tagging/
backfill_tags.py`.

**Walk:** Tag policy enforces `required_tags` on all new objects. Existing
objects are backfilled opportunistically. Eval suite asserts tag completeness
on new objects weekly.

**Run:** Tag policy blocks object creation if required tags are missing.
No exceptions. Untagged objects created before Run stage are tracked as
accepted technical debt in `decisions.md`.

---

## Part 5 — Governance Eval Suite

*References: PHILOSOPHY.md §Maturity Model — Walk exit criteria*

The eval suite is the verification layer. Terraform declares intent. The eval
suite asserts that the live environment matches it.

All assertions run via the `AUDITOR` role — read-only, no elevated
permissions.

### Assertion Categories

**Privilege assertions** (`tests/eval/test_rbac.py`)
- No user holds direct object grants
- ANALYST role cannot INSERT or CREATE on any schema
- CONN_{INTEGRATION} roles cannot access databases outside their declared
  `target_db` in `connectors.yaml`
- No service account holds a functional role directly

**Break-glass assertions** (`tests/eval/test_breakglass.py`)
- FIREFIGHTER has zero active user assignments
- Zero FIREFIGHTER sessions in query history in the last 30 days
- Alert triggered if either assertion fails

**Tagging completeness assertions** (`tests/eval/test_tagging.py`)
- All warehouses have required tags
- All databases and schemas created in the last 7 days have required tags
- Drift report: objects missing tags that were created before enforcement

**Cost anomaly assertions** (`tests/eval/test_cost.py`)
- No warehouse exceeded its resource monitor threshold in the last 7 days
- Query volume by role matches expected baseline (flags anomalous spikes)
- Credit consumption trend: week-over-week delta exceeding 20% surfaces as
  a finding

### Execution

```makefile
# Run eval suite locally (requires AUDITOR credentials in env)
make eval

# Run unit tests with mocked Snowflake connections (no cloud spend)
make test

# Run full CI pipeline (lint + unit tests + terraform plan)
make ci
```

Eval suite runs on a daily schedule via GitHub Actions. Findings are written
to a structured log and optionally posted to a Slack channel configured
during intake.

---

## Part 6 — Migration Runbook (Brownfield Path)

*References: PHILOSOPHY.md §Brownfield Compromise,
brownfield_intake.md Part 3 — Findings Summary*

See `runbooks/migration.md` for the full decision tree.

Summary of the approach:

**Principle:** parallel governance over hard cutover. Build the new model
alongside the existing one. Migrate one workload at a time. Use the eval
suite to measure drift. Never cut over until assertions pass.

**Sequence:** warehouses first → connector roles → human users → tag
enforcement → legacy role deprecation.

**Definition of done:** eval suite passes all assertions, zero direct grants
exist, FIREFIGHTER has no assigned users, all warehouses are monitored and
tagged, `decisions.md` is marked complete with sign-off date.

---

## Build Sequence

Given the above, the recommended build order for Claude Code:

```
Phase 1 — Foundation (this session, Crawl stage)
  1. terraform/modules/rbac/
     - Functional roles (static)
     - FIREFIGHTER (static, zero grants)
     - AUDITOR (static, account_usage read-only)
     - Object roles (for_each over connectors.yaml)
     - Connector roles (for_each over connectors.yaml)
     - Grants (derived from connectors.yaml privileges field)
  2. terraform/modules/warehouses/
     - Workload warehouses (derived from connectors.yaml warehouse field)
     - Resource monitors (defaults + overrides from connectors.yaml)
  3. terraform/modules/databases/
     - Databases and schemas (derived from connectors.yaml target_db field)
  4. terraform/main.tf
     - Wire modules together, pass connectors.yaml as variable

Phase 2 — Observability (Walk stage)
  5. terraform/modules/tags/
     - Tag objects (from tags.yaml)
     - Tag policies (Walk enforcement)
  6. tests/eval/
     - All four assertion modules
     - conftest.py with AUDITOR fixtures
  7. .github/workflows/terraform-plan.yml
  8. Makefile

Phase 3 — Hardening (Run stage)
  9. Tag policy enforcement (block on missing required tags)
  10. FIREFIGHTER reconciliation alert automation
  11. Quarterly privilege review automation
  12. runbooks/migration.md

Phase 4 — Publication
  13. README.md (maturity model framing, architecture guide)
  14. Blog post draft
```

---

## Initial Task for Claude Code

**Start here:** Generate Phase 1, Step 1 — the RBAC module.

Use the example `connectors.yaml` defined in this spec (Section 1.2) as the
input. The output should be a working Terraform module at
`terraform/modules/rbac/` that:

- Defines functional roles as static resources with inline comments
  referencing PHILOSOPHY.md
- Defines FIREFIGHTER as a dormant role with zero user grants and a comment
  documenting the emergency activation process
- Defines AUDITOR as a read-only role scoped to `snowflake.account_usage`
- Generates object roles and connector roles via `for_each` over
  `connectors.yaml`
- Applies grants derived from the `privileges` field in `connectors.yaml`
- Handles the Snowpipe `extra_grants` case explicitly
- Includes inline HCL comments explaining the reasoning behind each role
  boundary, referencing PHILOSOPHY.md by section

Use the `snowflake-labs/snowflake` Terraform provider. Pin the provider
version. Document the pinned version in a comment in `main.tf`.

### YAML-to-Terraform Bridge

`connectors.yaml` is loaded in HCL using the native `yamldecode` + `file`
pattern. No external script or code generation step is required. The
pattern for the RBAC module is:

```hcl
# terraform/modules/rbac/variables.tf
variable "connectors_file" {
  description = "Path to intake/connectors.yaml"
  type        = string
  default     = "${path.module}/../../../intake/connectors.yaml"
}

# terraform/modules/rbac/connectors.tf
locals {
  connectors = yamldecode(file(var.connectors_file)).connectors
}

resource "snowflake_account_role" "connector" {
  for_each = { for c in local.connectors : c.name => c }
  name     = "CONN_${each.key}"
  comment  = each.value.reason
}

resource "snowflake_grant_privileges_to_account_role" "connector_object" {
  for_each   = { for c in local.connectors : c.name => c }
  role_name  = snowflake_account_role.connector[each.key].name
  privileges = each.value.privileges

  on_schema {
    schema_name = "${each.value.target_db}.${
      each.value.target_schemas[0] == "*"
        ? "<all schemas>"
        : each.value.target_schemas[0]
    }"
  }
}
```

The same pattern applies to `tags.yaml` for the tags module. Changing the
environment configuration is always a YAML edit followed by `terraform apply`
— never a direct HCL change to the modules themselves.

---

*Flynn Data Services · flynndata.com · Last reviewed: March 2026*

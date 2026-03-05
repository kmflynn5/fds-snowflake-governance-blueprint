# Project: Snowflake Governance & IaC Maturity Blueprint — "Golden Path" Template Repo

**Role:** Act as a Principal Data Platform Engineer with deep experience governing Snowflake environments for B2B SaaS companies at the 1-2 person data team stage. Be opinionated. Write like someone who has actually done this and knows where it breaks down.

---

## Background & Audience

I'm a fractional data engineer (Flynn Data Services) building reusable technical assets for B2B SaaS clients ($5M–$50M ARR). This repo will serve two purposes:

1. A credible, working reference I can walk through on client and recruiter calls tomorrow
2. A publishable GitHub repo + blog post that demonstrates my governance philosophy

**Target client profile:** data teams that have grown ad-hoc, no tagging standards, overpermissioned roles, no cost attribution by team or project. They need a path from chaos to governed without blowing up their existing workflows.

---

## Project Goal

Build a "Golden Path" repository that demonstrates a high-maturity Snowflake environment using Terraform. The repo should be immediately forkable by a client and structured around a crawl/walk/run maturity model so they can see where they are today and what's next.

---

## Key Architecture Requirements

### 1. Functional RBAC Hierarchy (Least Privilege)

Build a Terraform module implementing a three-tier role hierarchy:

- **Object Roles:** Low-level roles with direct access to schemas/tables
- **Functional Roles:**
  - `LOADER` — ingestion (Fivetran/Airflow). Write access to RAW schemas only
  - `TRANSFORMER` — dbt. Read RAW, write to ANALYTICS/MARTS
  - `ANALYST` — read-only access to final MARTS
- **Account Roles:** Users and service accounts assigned to functional roles above
- **Break-Glass Role:** A dormant `FIREFIGHTER` role with elevated permissions, no assigned users by default, documented for emergency use with a reconciliation loop to alert if it ever gets assigned

The hierarchy should enforce least privilege at every layer. Document the "why" behind each role boundary in the README — most clients understand RBAC conceptually but not why the boundaries are drawn where they are.

### 2. Cost & Performance Optimization

Implement a "Warehouse per Workload" strategy:

- Dedicated warehouses: `WH_INGEST`, `WH_TRANSFORM`, `WH_ANALYTICS`
- Resource Monitors attached to each warehouse with specific credit quotas and alert thresholds (warn at 75%, suspend at 100%)
- Query tagging via Snowflake session parameters so every query is attributed to a cost center

### 3. Tagging Taxonomy (the part most teams skip)

This is where clients struggle most in practice — anyone can set up RBAC, few have a coherent tagging strategy. Build a `/terraform/modules/tags` section with an opinionated taxonomy covering:

- **Cost attribution tags:** `cost_center`, `team`, `project`, `environment` (prod/dev/staging)
- **Data classification tags:** `sensitivity` (public/internal/confidential/restricted), `pii` (true/false)
- **Operational tags:** `owner`, `created_by`, `last_reviewed`

Apply tags at the database, schema, and warehouse level. Include a policy that enforces required tags on all new objects via a Snowflake object tagging policy. Document which tags are required vs optional and why.

### 4. Governance & Quality Guardrails

- **Local-first:** Makefile or task runner for local linting (`sqlfluff`, `ruff`) and testing (`pytest`)
- **Mocking:** Python sample using `pytest` that mocks Snowflake connections for local testing without cloud spend
- **CI/CD:** GitHub Actions workflow that runs `terraform plan` on every PR to prevent unauthorized permission changes. Any RBAC or tag policy change requires a plan review before merge

### 5. Maturity Model (Crawl / Walk / Run)

Structure the README around three maturity stages so a client can self-assess and see a clear path forward:

| Stage | Capabilities |
|-------|-------------|
| **Crawl** | RBAC hierarchy in place, warehouses separated by workload, basic resource monitors |
| **Walk** | Query tagging enforced, cost attribution by team/project, CI/CD for Terraform changes, local testing setup |
| **Run** | Object tagging policy enforced on all new objects, FIREFIGHTER reconciliation alerts, full observability dashboard (Snowflake cost + query performance), dbt test coverage gates in CI |

Each stage should be a discrete, deployable increment — not a big bang. Clients adopt this incrementally, not all at once.

---

## Repo Structure

```
/terraform
  /modules
    /rbac          # role hierarchy, grants
    /warehouses    # WH per workload + resource monitors
    /tags          # tag taxonomy + object tag policies
    /databases     # database + schema structure
  main.tf
  variables.tf
  outputs.tf

/scripts
  /tagging         # Python automation for backfilling tags on existing objects
  /user_onboarding # Service account provisioning script

/tests
  /unit            # pytest with Snowflake connection mocks

Makefile
README.md          # Maturity model + architecture guide
.github/workflows/terraform-plan.yml
```

---

## Tone & Approach

Practical and opinionated. Not a vendor whitepaper. Every design decision should have a one-line "why" comment in the code or README. If there's a common mistake or anti-pattern, call it out explicitly — that's what makes this useful to a real client rather than a generic template.

---

## Initial Task

Generate the Terraform directory structure and `main.tf` for the RBAC hierarchy (`LOADER` → `TRANSFORMER` → `ANALYST` → `FIREFIGHTER`) using the `snowflake-labs/snowflake` provider. Ensure roles are linked correctly, grants are explicit, and include inline comments explaining the reasoning behind each role boundary.

<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Expansion Pack: Observability

*Flynn Data Services — Additive expansion on top of Core*

## What It Includes

This expansion adds two deliverables and one new role to the RBAC hierarchy:

**AUDITOR role** — a persistent, read-only functional role added to the Snowflake environment
as part of this expansion. It has access to `SNOWFLAKE.ACCOUNT_USAGE` and
`INFORMATION_SCHEMA` but no access to data. This is distinct from the temporary
`FDS_AUDITOR_USER` created during a brownfield audit — the AUDITOR role is a standing role
used by the eval suite on an ongoing basis. It is represented as a static Terraform resource
in `terraform/modules/rbac/`.

**Tag eval suite** — a scheduled Python script (consistent with `scripts/audit.py`) that
connects via the AUDITOR role and checks rules defined in `intake/tags.yaml` against live
object metadata. Each rule produces a pass/fail with the specific offending objects listed.
Output is a structured JSON report consumed two ways:
1. A GitHub Actions workflow that runs nightly and posts a summary to Slack (or wherever
   ops updates live).
2. An Evidence dashboard page that visualizes compliance trends over time: percent compliant
   this week vs. last week, which teams are creating untagged objects.

**Evidence dashboard** — a local Evidence.dev dashboard with two views: tag compliance trends
(powered by the eval suite JSON output) and cost attribution by team (powered by
`WAREHOUSE_METERING_HISTORY`, joined against the `cost_center` and `owner` tags on
warehouses). Both views are in the same dashboard — there is one dashboard, not three
separate artifacts.

**Prerequisite:** `cost_center` and `owner` tags must be defined in `intake/tags.yaml` during
Core intake (they are included in the default taxonomy). This expansion surfaces those tags in
cost reporting — it does not add them. If they were omitted during intake, update `tags.yaml`
and re-run codegen before deploying this expansion.

## When to Adopt

This expansion is right for a team that wants visibility before committing to enforcement.
Common triggers:

- A second team starts creating objects in Snowflake and you want to verify they're following
  the tagging convention
- You onboard a new connector and want to confirm it's tagged correctly before it generates
  meaningful spend
- Your monthly Snowflake bill crosses a threshold where cost attribution by team matters
- You're preparing for an Enforcement expansion and need a baseline compliance picture first

Enforcement can be added later without rework.

## Done Criteria

**Setup — verified once during deployment:**
- [ ] AUDITOR role exists in Snowflake with correct `ACCOUNT_USAGE` grants
- [ ] Every database has a `cost_center` tag
- [ ] Every warehouse has an `owner` tag
- [ ] Evidence dashboard is deployed and both views (compliance + cost) are populated

**Operational — continuously true:**
- [ ] Eval suite running on schedule (daily GitHub Actions job)
- [ ] GitHub Actions posts nightly tag compliance summary to Slack
- [ ] Drift is visible within 24 hours of a non-compliant object being created

---

*Flynn Data Services · flynndata.com · See also: [EXPANSION_ENFORCEMENT.md](EXPANSION_ENFORCEMENT.md)*

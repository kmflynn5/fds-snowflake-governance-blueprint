<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Expansion Pack: Observability

*Flynn Data Services — Additive expansion on top of Core*

## What It Includes

- **Tag eval suite** — a scheduled Python script (consistent with `scripts/audit.py`) that
  connects via the AUDITOR role, queries `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES` and
  `INFORMATION_SCHEMA`, and checks rules defined in `intake/tags.yaml`. Each rule produces
  a pass/fail with the specific offending objects listed.
- **Cost attribution via warehouse tags** — every database, schema, and warehouse is tagged
  with `cost_center` and `owner`, enabling cost breakdowns in `WAREHOUSE_METERING_HISTORY`
  by team and project.
- **WAREHOUSE_METERING_HISTORY audit trail** — structured query history by role and warehouse
  surfaces credit consumption trends and anomalous spikes week-over-week.
- **Evidence dashboard** — a local Evidence.dev dashboard that visualizes compliance trends
  over time: percent compliant this week vs. last week, which teams are creating untagged
  objects, credit burn by cost center.

The eval suite output is a structured JSON report consumed in two ways:
1. A GitHub Actions workflow that runs nightly and posts a summary to Slack (or wherever
   ops updates live).
2. The Evidence dashboard page showing compliance trends over time.

## When to Adopt

This expansion is right for a small to mid-size team that is ready for visibility but
where enforcement feels premature or would create too much operational overhead. If your
team is disciplined and you trust that drift will be caught and corrected manually, start
here. Enforcement can be added later without rework.

## Done Criteria

- [ ] Eval suite running on schedule (daily GitHub Actions job)
- [ ] Every database has a `cost_center` tag
- [ ] Every warehouse has an `owner` tag
- [ ] Evidence dashboard shows percent compliant week-over-week
- [ ] GitHub Actions posts nightly tag compliance summary to Slack
- [ ] Drift is visible within 24 hours of a non-compliant object being created

---

*Flynn Data Services · flynndata.com · See also: [EXPANSION_ENFORCEMENT.md](EXPANSION_ENFORCEMENT.md)*

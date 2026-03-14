<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Snowflake Governance Intake — Greenfield
*Flynn Data Services · References: PHILOSOPHY.md*

This questionnaire is completed before any Terraform is written. The answers
drive the `connectors.yaml`, the warehouse topology, the tagging taxonomy,
and the `decisions.md` that documents why the environment is structured as it
is.

There are no right answers. The goal is to surface decisions you haven't made
yet and give you opinionated defaults where you don't have a preference.

---

## Section 1 — Context

**1.1 What is the primary purpose of this Snowflake environment?**
- [ ] Analytics / BI (reporting, dashboards, ad-hoc queries)
- [ ] Data platform (multiple teams, multiple use cases)
- [ ] Product analytics (event data, user behavior)
- [ ] Operational / reverse-ETL (syncing data back to operational systems)
- [ ] Mixed — describe: _______________

**1.2 How many people will actively use this environment at launch?**

| Role | Count |
|------|-------|
| Data engineers | |
| Analysts / BI | |
| Data scientists | |
| Service accounts (integrations) | |

**1.3 What is your current maturity target?**
- [ ] Core — get the structure right, eliminate the worst anti-patterns
- [ ] Observability — core plus full observability and cost attribution
- [ ] Enforcement — full automated enforcement from day one

*If unsure, start with Core. See PHILOSOPHY.md — The Maturity Model.*

---

## Section 2 — Ingestion (the LOADER layer)

*Each ingestion tool gets its own connector role. See PHILOSOPHY.md —
The Connector Role Philosophy.*

**2.1 List every tool or process that will write data into Snowflake:**

| Integration name | Type | Target database | Target schemas | Notes |
|-----------------|------|-----------------|----------------|-------|
| | ETL/ELT tool | | | e.g. Fivetran, Airbyte, Integrate.io |
| | Orchestrator | | | e.g. Airflow, Prefect, Dagster |
| | Event stream | | | e.g. Snowpipe, Kafka connector |
| | Custom script | | | |
| | | | | |

**2.2 For each integration above: does it need read-back access to its own
schemas after writing?**
*(Some tools query what they just wrote for deduplication or incremental
logic.)*

| Integration | Needs read-back? | Schemas |
|-------------|-----------------|---------|
| | Yes / No | |

**2.3 Are any integrations managed by an external vendor (i.e. you do not
control the service account)?**
- [ ] Yes — list them: _______________
- [ ] No

*Note: vendor-managed service accounts should still get dedicated connector
roles with the minimum required grants. You control the role even if you do
not control the credential.*

---

## Section 3 — Transformation (the TRANSFORMER layer)

**3.1 What tool handles transformation?**
- [ ] dbt Core
- [ ] dbt Cloud
- [ ] Custom Python / SQL scripts
- [ ] Spark / other
- [ ] Not yet decided

**3.2 What databases/schemas does the transformer need to read from?**
*(Typically all RAW databases)*

**3.3 What databases/schemas does the transformer need to write to?**
*(Typically ANALYTICS, MARTS, or equivalent)*

**3.4 Does your transformation layer need to create schemas dynamically?**
- [ ] Yes — dbt creates schemas per environment/target
- [ ] No — schemas are pre-created and static

*If yes: `CREATE SCHEMA` privilege is required on the target database. This
will be scoped as narrowly as possible.*

**3.5 How many transformer service accounts do you need?**
- [ ] One (single dbt project / transformation pipeline)
- [ ] Multiple — describe: _______________ *(e.g. separate prod and dev
  service accounts, separate pipelines per domain)*

---

## Section 4 — Consumption (the ANALYST layer)

**4.1 What tools will analysts use to query data?**
- [ ] Looker
- [ ] Tableau
- [ ] Mode
- [ ] Metabase
- [ ] Direct SQL (Snowsight / DBeaver / etc.)
- [ ] Other: _______________

**4.2 Do BI tools connect via a shared service account or individual user
credentials?**
- [ ] Shared service account per tool
- [ ] Individual user credentials
- [ ] Mixed — describe: _______________

*Shared service accounts for BI tools are acceptable and common. They follow
the same connector role pattern as ingestion tools.*

**4.3 Do you need separate access tiers for analysts?**
*(e.g. some analysts can query raw data, others only MARTS)*
- [ ] No — all analysts get the same read access
- [ ] Yes — describe tiers: _______________

**4.4 Do any analysts need write access to any schemas?**
*(e.g. uploading reference data, writing back model outputs)*
- [ ] No
- [ ] Yes — describe: _______________

---

## Section 5 — Warehouse Topology

*Default pattern: one warehouse per workload (WH_INGEST, WH_TRANSFORM,
WH_ANALYTICS). Deviations require a documented reason.*

**5.1 Are there workloads that warrant a dedicated warehouse beyond the
defaults?**
*(e.g. a high-volume event pipeline that would compete with standard
ingestion, a heavy ML workload)*
- [ ] No — defaults are sufficient
- [ ] Yes — describe: _______________

**5.2 What are your initial warehouse sizing preferences?**

| Warehouse | Initial size | Auto-suspend (minutes) |
|-----------|-------------|----------------------|
| WH_INGEST | XS / S / M | |
| WH_TRANSFORM | XS / S / M | |
| WH_ANALYTICS | XS / S / M | |

*If unsure: start XS for all, auto-suspend at 5 minutes. Right-size after
observing actual usage.*

**5.3 What credit budget should resource monitors enforce per warehouse per
month?**

| Warehouse | Monthly credit limit | Alert at (%) | Suspend at (%) |
|-----------|--------------------|--------------|--------------------|
| WH_INGEST | | 75 | 100 |
| WH_TRANSFORM | | 75 | 100 |
| WH_ANALYTICS | | 75 | 100 |

---

## Section 6 — Database & Schema Structure

**6.1 What is your intended database structure?**

| Database name | Purpose | Owner team |
|--------------|---------|------------|
| | Raw ingestion | |
| | Transformed / analytics | |
| | Final marts | |
| | Events (if separate) | |

*If unsure: a standard three-database pattern (RAW, ANALYTICS, MARTS) is the
default. Event data gets its own database if volume or retention requirements
differ.*

**6.2 Within RAW: one database per source or one shared RAW database with
schemas per source?**
- [ ] One database per source (e.g. RAW_FIVETRAN, RAW_AIRFLOW) — stronger
  isolation, easier connector role scoping
- [ ] One shared RAW database, schemas per source — simpler structure, less
  isolation
- [ ] Not sure — recommend default

*Default recommendation: one database per source for environments with 3+
ingestion tools. One shared database is acceptable for simpler environments.*

---

## Section 7 — Tagging

*Required at Walk stage. Collected now to inform database/schema structure
decisions.*

**7.1 How do you want to attribute Snowflake costs?**
- [ ] By team (data engineering, analytics, product, etc.)
- [ ] By project or workstream
- [ ] By environment (prod, dev, staging)
- [ ] By cost center (finance category)
- [ ] Not yet decided

**7.2 List the teams or cost centers that will appear in cost attribution:**

| Tag value | Description |
|-----------|-------------|
| | |

**7.3 Do you have any data classification requirements?**
*(PII handling, sensitivity levels, regulatory requirements)*
- [ ] Yes — describe: _______________
- [ ] No

---

## Section 8 — Emergency Access (FIREFIGHTER)

*See PHILOSOPHY.md — Core Principles #4.*

**8.1 Who is authorized to activate the FIREFIGHTER role in an emergency?**

| Name | Title | Contact |
|------|-------|---------|
| | | |

**8.2 What is the notification process when FIREFIGHTER is activated?**
*(e.g. Slack channel, PagerDuty alert, email)*

**8.3 What is the expected deactivation SLA?**
*(How quickly should FIREFIGHTER be unassigned after an incident is
resolved?)*
- [ ] Same day
- [ ] Within 24 hours
- [ ] Defined per-incident

---

## Section 9 — Decisions Log

*Completed by the engineer after the intake session. This becomes
`decisions.md` in the repo.*

| Decision | Options considered | Choice made | Reason | Reference |
|----------|-------------------|-------------|--------|-----------|
| Database structure | Per-source vs shared RAW | | | PHILOSOPHY.md §Connector Role Philosophy |
| Warehouse sizing | XS / S / M per workload | | | |
| Maturity target | Core / Observability / Enforcement | | | PHILOSOPHY.md §Maturity Model |
| | | | | |

---

*Flynn Data Services · flynndata.com · Last reviewed: March 2026*

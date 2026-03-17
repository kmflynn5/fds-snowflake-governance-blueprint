<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# The Snowflake Governance Philosophy
*Flynn Data Services — Internal Standard v1.1*

This document defines the governance philosophy behind every Snowflake
environment I design and implement. It exists for one reason: every
downstream decision — role design, warehouse topology, tagging strategy,
migration sequencing — should be traceable back to a principle, not a
preference.

If a client asks "why is it structured this way?", the answer lives here.

---

## Why This Exists

Most Snowflake environments I've inherited share the same origin story.

A small data team stood up a warehouse quickly, made pragmatic shortcuts
under deadline pressure, and then watched those shortcuts calcify into
institutional patterns. ACCOUNTADMIN gets shared because setting up proper
roles "takes too long." A single service account gets reused across three
tools because "it already has the right access." Tags never get implemented
because there's always something more urgent.

Two years later, nobody knows who has access to what, costs are
unattributable, and the "quick" shortcuts are load-bearing infrastructure
that nobody wants to touch.

This framework exists to interrupt that pattern — ideally before it starts,
but also after it's already taken hold.

---

## Core Principles

These are non-negotiable. They apply at every maturity stage, in every
client environment, greenfield or brownfield.

### 1. One service account per use case

Every integration gets its own dedicated service account and connector role.
Fivetran gets one. Airflow gets one. Your custom ingestion script gets one.
They are never shared.

Why it matters: when a credential is compromised, rotated, or an integration
is offboarded, the blast radius is exactly one workload. Shared service
accounts make all three of those operations dangerous and expensive.

The objection I hear most: "it's more accounts to manage." That's true. It
is also the correct tradeoff.

### 2. No human user ever holds direct object grants

Human users are assigned to functional roles. Functional roles inherit from
object roles. Object roles hold the actual privileges. The chain is always:
user → functional role → object role → privilege.

Direct grants to human users bypass the entire governance model. They
accumulate silently, are invisible in role hierarchy audits, and become
unmaintainable at any non-trivial team size.

### 3. No service account holds a functional role directly

Service accounts are assigned to connector roles. Connector roles are scoped
to the minimum required database, schema, and privilege set for that specific
integration. LOADER, TRANSFORMER, and ANALYST are conceptual layer names used
in documentation and architecture diagrams — they are not Snowflake roles and
nothing is assigned to them.

This is the most commonly misunderstood part of the model. LOADER does not
mean "has write access to RAW." It means "is the conceptual category that
connector roles for ingestion tools belong to." The actual access is always
more specific. The layer a role belongs to is communicated through naming
conventions (`CONN_` prefix = loader/transformer layer, human functional role
names = analyst layer) and role comments. A `role_layer` tag on each role is
planned for the Observability expansion to make this queryable.

### 4. ACCOUNTADMIN is never a workaround

ACCOUNTADMIN should have zero active user assignments in a production
environment. It exists for account-level administration during initial setup
and emergency intervention only.

If someone asks for ACCOUNTADMIN access to solve a problem, the correct
response is to identify what privilege is actually needed and grant that
specifically. ACCOUNTADMIN is not a debugging tool.

### 5. Every privilege grant has a documented reason

If you cannot articulate why a grant exists, it should not exist. This is
not bureaucracy — it is the minimum bar for maintainability. Undocumented
grants are the primary source of privilege creep in every environment I have
audited.

In practice this means: connector roles are defined in config with an
explicit `reason` field, this document is referenced in every Terraform
module README, and the intake process produces a `decisions.md` that records
why each design choice was made for this specific client.

### 6. Start more restrictive, open up deliberately

When uncertain about the correct privilege scope, start with less access and
expand based on observed need. Never start permissive and restrict later.

Restriction after the fact breaks things. Expansion after the fact is
controlled and documented. The asymmetry matters.

### 7. Object ownership is always transferred to a central role

In Snowflake, OWNERSHIP is the most powerful privilege. By default, the role
that creates an object owns it. This means connector roles — which create
tables, schemas, and pipes — own those objects unless ownership is explicitly
transferred. Orphaned ownership (ownership held by a deprecated or
compromised role) is one of the most dangerous and hardest-to-audit failure
modes in a Snowflake environment.

The rule: all objects created by connector roles have ownership transferred
to `SYSADMIN` immediately after creation, using `GRANT OWNERSHIP ... TO ROLE
SYSADMIN COPY CURRENT GRANTS`. The `COPY CURRENT GRANTS` clause is mandatory
— without it, existing grants on the object are silently dropped during the
transfer.

In Terraform, this is enforced via the `snowflake_grant_ownership` resource
applied after every object creation. In brownfield environments, the
environment survey explicitly audits for non-SYSADMIN ownership as a
critical finding.

### 8. Service accounts use key-pair authentication

Password-based authentication for service accounts is a known security risk.
Passwords can be leaked, are hard to rotate reliably across dependent
systems, and provide no audit trail of credential access.

All service accounts defined in `connectors.yaml` must use RSA key-pair
authentication. The private key is stored in a secrets manager (not in the
repo). The public key is managed via Terraform.

Password-based auth for service accounts is an acceptable Core stage
compromise only when migrating an existing environment where rotation
requires coordinating with a vendor. It must be documented in `decisions.md`
with a target remediation date and must be resolved before adopting the
Observability expansion.

### 9. Storage integrations are privileged objects

External stages and storage integrations (S3, GCS, Azure Blob) are a common
vector for PII leakage. An analyst with access to an external stage can
query raw cloud storage directly, bypassing all data classification and
masking controls applied at the warehouse layer.

Storage integrations are never granted to functional roles. They are granted
only to the specific `CONN_{INTEGRATION}` role that requires direct cloud
storage access — typically a Snowpipe connector or a custom ingestion
service account. No other role inherits this grant.

In practice: `CONN_SNOWPIPE_SNOWPLOW` can access the Snowplow S3 bucket.
Human functional roles, other connector roles, and object roles cannot.

---

## The Least Privilege Standard

Least privilege is not a setting. It is a design discipline that operates at
every layer of the environment.

**At the database level:** service accounts are scoped to the specific
database their workload requires. A Fivetran connector writing to
`RAW_FIVETRAN` has no visibility into `RAW_AIRFLOW` or `ANALYTICS`.
Cross-database access is explicit and documented, never inherited.

**At the schema level:** object roles are scoped to specific schemas where
possible. A connector loading Snowplow events writes to `EVENTS.SNOWPLOW`
only — not to the entire EVENTS database.

**At the privilege level:** write access and read access are always separate
grants. The ability to INSERT does not imply the ability to SELECT. The
ability to CREATE TABLE does not imply the ability to DROP TABLE. Each
privilege is granted because it is required, not because it is convenient.

**On future grants:** `GRANT ... ON FUTURE OBJECTS` is powerful and
dangerous. It is used deliberately and documented explicitly. It is never
applied at the database level to a broad role — only at the schema level to
a narrowly scoped object role.

**The practical test:** for every role in the environment, you should be able
to answer "what is the minimum this role needs to do its job, and does it
have exactly that?" If the answer requires research, the model has drifted.

---

## The Connector Role Philosophy

The standard three-tier RBAC model (LOADER → TRANSFORMER → ANALYST) is a
useful mental model and a poor implementation target.

The problem: LOADER implies a single role with write access to the RAW layer.
In practice, your RAW layer is never monolithic. Fivetran writes to its own
isolated database. Airflow writes to a different location. A Snowpipe
ingesting event streams from S3 writes to a third. Treating all of these as
a single LOADER role means a compromised Fivetran credential has write access
to your Airflow schemas and your event streams. That is not least privilege.

The solution is a connector layer that sits between object roles and
functional roles:

```
CONN_{INTEGRATION}               # one per tool/service account
  └── OBJ_{DB}_{SCOPE}_WRITER    # scoped to specific db/schema
  └── WH_{WORKLOAD}_USAGE
```

LOADER, TRANSFORMER, and ANALYST remain in the model as conceptual layer
names — useful for documentation and communicating intent. They are not
Snowflake roles. The layer each role belongs to is expressed through naming
conventions and role comments. A `role_layer` tag (values: `loader`,
`transformer`, `analyst`, `human_functional`, `emergency`, `audit`) is
planned for the Observability expansion to make layer membership queryable
via `account_usage.tag_references`.

The connector layer is defined in `connectors.yaml` and generated by
Terraform. Adding a new integration is a YAML entry, not a Terraform module
change. Removing an integration is a YAML deletion and a `terraform apply`.
The model is designed to be maintained, not just implemented.

---

## The Warehouse Isolation Standard

Dedicated warehouses per workload is the baseline. The additional question
is how each warehouse scales — and the answer differs by workload type.

**High-concurrency workloads (BI tools, ad-hoc analyst queries):** use
multi-cluster warehouses. When multiple users query simultaneously, a
single-cluster warehouse queues requests. Multi-cluster auto-scales
horizontally to eliminate queuing. `WH_ANALYTICS` is always multi-cluster
in production environments with more than two active analysts.

**Batch workloads (ETL ingestion, dbt transformation):** use single-cluster
warehouses sized for throughput. These workloads run sequentially or in
controlled parallelism — horizontal scaling adds cost without benefit.
`WH_INGEST` and `WH_TRANSFORM` are single-cluster, sized up (M or L) during
active windows and auto-suspended between runs.

**The noisy neighbor rule:** no two workload types share a warehouse,
regardless of cost pressure. A long-running dbt transformation competing
with analyst queries degrades both. The cost of an extra warehouse is lower
than the operational cost of unpredictable query performance.

**Scaling decisions are documented in `decisions.md`.** If a client chooses
single-cluster for `WH_ANALYTICS` due to cost constraints, that decision is
recorded with the tradeoff acknowledged and a threshold defined for when to
revisit (e.g. "revisit when concurrent analyst count exceeds 5").

---

## The Maturity Model

Governance is not a state you achieve. It is a capability you build
incrementally. This framework is structured around three maturity stages —
not because lower stages are acceptable endpoints, but because incremental
adoption is more likely to succeed than big-bang governance projects.

### Core — Structural Integrity

**Goal:** The hierarchy is correct and the worst anti-patterns are
eliminated.

At this stage:
- RBAC hierarchy is implemented and documented
- All service accounts have dedicated connector roles
- No human user holds direct object grants
- ACCOUNTADMIN has no active user assignments
- Warehouses are separated by workload with resource monitors attached
- A `decisions.md` documents why the environment is structured as it is

What is not required at this stage: complete tag coverage, CI/CD enforcement,
automated eval suite. The structure is right. Enforcement is still partly
manual.

**Exit criteria:** The eval suite's privilege assertions pass. No direct
grants exist. FIREFIGHTER has zero assigned users.

### Observability Expansion

**Goal:** You can see what is happening and know when something drifts.

Everything from Core plus:
- Tagging enforced on all new objects (cost center, owner, environment)
- Cost attribution working by team and project
- Eval suite running on a schedule, findings reviewed weekly
- CI/CD running `terraform plan` on all RBAC changes
- Query history monitoring active — FIREFIGHTER usage triggers an alert

What is not required at this stage: automated blocking of non-compliant
objects, full historical tag backfill. You have visibility. Remediation is
still partly manual.

**Exit criteria:** Eval suite runs clean. Cost is attributable. Drift is
visible within 24 hours.

### Enforcement Expansion

**Goal:** Drift is impossible, not just visible.

Everything from Observability plus:
- Tag policies block untagged object creation at the database level
- All RBAC changes require a passing `terraform plan` review before merge
- FIREFIGHTER assignment triggers an automated incident
- New connector roles are generated from YAML — no manual Terraform authoring
- Quarterly privilege review is automated — eval suite produces a findings
  report, not a manual audit
- **Terraform is the authoritative source of truth.** Any delta surfaced by
  `terraform plan` that was not initiated via a pull request is treated as a
  security incident, not a configuration drift to be silently reconciled. The
  assumption is that an unexpected plan delta means something was changed
  outside the governed process — manually, via the Snowsight UI, or via a
  compromised credential.

**Exit criteria:** The environment self-defends. A new engineer cannot
accidentally introduce a privilege escalation or an untagged object without
it surfacing immediately.

---

## The Brownfield Compromise

Most clients are not greenfield. They have an existing environment with
active users, running workloads, legacy grants, and institutional muscle
memory built around doing things the wrong way.

The philosophy does not change in brownfield environments. The timeline does.

The guiding principle is **parallel governance**: build the correct model
alongside the existing one, migrate workloads one at a time, and use the
eval suite to measure drift between the declared state and the actual state
until the legacy model is fully deprecated. Never attempt a hard cutover.

Specific compromises that are acceptable during migration:

- A legacy service account retaining broad grants while its workload is being
  migrated to a connector role. Acceptable temporarily, documented with a
  target remediation date.
- ACCOUNTADMIN retained by one named individual during the migration window
  for emergency intervention. Acceptable temporarily, with an explicit
  offboarding date agreed upfront.
- Incomplete tag coverage on historical objects. Acceptable permanently for
  pre-migration objects — enforce going forward, backfill opportunistically.

Compromises that are never acceptable regardless of migration stage:

- New service accounts created outside the connector role pattern
- New human users assigned direct object grants
- New workloads assigned to ACCOUNTADMIN or SYSADMIN

The migration runbook (`/runbooks/migration.md`) operationalizes this
philosophy for brownfield environments. The intake process
(`/intake/brownfield_survey.md`) surfaces the existing state before any
migration work begins.

---

## What This Framework Does Not Cover

This framework is deliberately scoped. The following are real governance
concerns that are out of scope here:

**Row-level security and dynamic data masking** — important for multi-tenant
data models and regulated data, covered by a separate policy framework.

**Data sharing policies** — Snowflake's data sharing capabilities introduce
a distinct set of governance questions around consumer access and data
contracts. Out of scope here.

**dbt project governance** — model naming conventions, schema organization,
and test coverage standards are downstream of warehouse governance but are
their own discipline.

**Data retention and deletion policies** — GDPR/CCPA compliance at the data
level is a legal and data classification problem, not an access control
problem. Related but separate.

Scope creep is how governance projects fail. If a client raises one of these
topics during an engagement, the correct response is to acknowledge it,
document it as a future workstream, and keep the current engagement focused.

---

## A Note on Pragmatism

This document is opinionated. Opinionated frameworks are more useful than
flexible ones because they make decisions so you do not have to make them
under deadline pressure.

That said: the goal is a governed environment that the client's team can
maintain and understand, not a perfect implementation of a theoretical model.
When a principle conflicts with a client's operational reality, document the
conflict, agree on a remediation path, and move forward. A good governance
model that gets adopted is worth more than a perfect one that does not.

The non-negotiables listed above are non-negotiable. Everything else is a
conversation.

---

*Flynn Data Services · flynndata.com · Last reviewed: March 2026*

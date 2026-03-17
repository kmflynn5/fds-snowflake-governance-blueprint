<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Snowflake Governance Intake — Brownfield
*Flynn Data Services · References: PHILOSOPHY.md*

This document is completed before any changes are made to an existing
Snowflake environment. It has two parts:

1. **Environment Survey** — an automated audit of the current state
2. **Targeted Interview** — structured questions to surface intent, history,
   and constraints that the audit cannot capture

The survey runs first. The interview is conducted after reviewing the survey
output. Together they produce a `decisions.md` and a migration plan that is
realistic about what exists today.

*Guiding principle: understand before you touch anything.*

---

## Part 1 — Environment Survey

Run these queries against the existing environment using a read-only audit
session. Save all output to `/intake/survey_output/` before the interview.

### 1.1 Role Inventory

```sql
-- All account-level roles
SHOW ROLES;

-- Full grant hierarchy (who has what)
SELECT
  grantee_name,
  granted_on,
  name AS privilege_or_role,
  privilege,
  granted_to,
  grant_option,
  granted_by
FROM snowflake.account_usage.grants_to_roles
WHERE deleted_on IS NULL
ORDER BY grantee_name, granted_on, name;
```

**What to look for:**
- Roles with names that don't follow a clear convention (signals ad-hoc
  creation)
- Object roles that are also assigned to human users (direct grant violation)
- Roles with ACCOUNTADMIN or SYSADMIN in the hierarchy unexpectedly

### 1.2 User Inventory

```sql
-- All users and their default/active roles
SHOW USERS;

-- Users with ACCOUNTADMIN
SELECT grantee_name AS user_name
FROM snowflake.account_usage.grants_to_users
WHERE role = 'ACCOUNTADMIN'
  AND deleted_on IS NULL;

-- Service accounts (heuristic: no email, or email pattern suggests non-human)
SELECT name, login_name, email, default_role, last_success_login
FROM snowflake.account_usage.users
WHERE deleted_on IS NULL
ORDER BY last_success_login DESC NULLS LAST;
```

**What to look for:**
- Human users with ACCOUNTADMIN assigned
- Service accounts that haven't logged in recently (candidates for
  deactivation)
- Users with no default role set (will inherit PUBLIC only — often a
  misconfiguration)

### 1.3 Human User Role Assignments

```sql
-- Active human users and their current role assignments
SELECT
    u.name AS user_name, u.login_name, u.type AS user_type,
    g.role AS granted_role, u.last_success_login
FROM snowflake.account_usage.users u
LEFT JOIN snowflake.account_usage.grants_to_users g
    ON u.name = g.grantee_name
WHERE u.deleted_on IS NULL
    AND u.type NOT IN ('SERVICE', 'LEGACY_SERVICE')
ORDER BY u.last_success_login DESC NULLS LAST;
```

**What to look for:**
- Humans assigned to object roles directly (e.g. `OBJ_ANALYTICS_READER`) — should
  only hold functional roles
- SYSADMIN assignments used for daily work (should be reserved for infrastructure
  setup only)
- Users without a matching functional persona — signals ad-hoc role creation or
  missing team structure definition

### 1.5 Direct Object Grants to Users

```sql
-- Any privilege granted directly to a user (should be zero in a governed env)
SELECT *
FROM snowflake.account_usage.grants_to_users
WHERE granted_on != 'ROLE'
  AND deleted_on IS NULL;
```

**What to look for:**
- Any results here are findings. Direct object grants to users bypass the
  role hierarchy entirely.

### 1.6 Warehouse Inventory

```sql
-- All warehouses, sizing, and current state
SHOW WAREHOUSES;

-- Warehouse usage last 30 days
SELECT
  warehouse_name,
  COUNT(*) AS query_count,
  SUM(credits_used) AS total_credits,
  AVG(execution_time)/1000 AS avg_execution_seconds
FROM snowflake.account_usage.query_history
WHERE start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP)
  AND warehouse_name IS NOT NULL
GROUP BY warehouse_name
ORDER BY total_credits DESC;
```

**What to look for:**
- Warehouses with zero usage in 30 days (candidates for removal)
- Warehouses without resource monitors attached
- Single warehouse handling all workloads (ingestion, transformation, and
  analytics competing for the same compute)

### 1.7 Resource Monitor Coverage

```sql
-- Warehouses without resource monitors
SELECT w.name AS warehouse_name
FROM snowflake.account_usage.warehouses w
LEFT JOIN snowflake.account_usage.resource_monitors rm
  ON w.resource_monitor = rm.name
WHERE w.deleted_on IS NULL
  AND rm.name IS NULL;
```

**What to look for:**
- Any warehouse without a resource monitor is an uncontrolled cost exposure.

### 1.8 Tag Coverage

```sql
-- Objects with tags applied
SELECT *
FROM snowflake.account_usage.tag_references
WHERE object_deleted IS NULL
ORDER BY object_database, object_schema, object_name;

-- Databases and schemas with no tags
SELECT
  table_catalog AS database_name,
  table_schema AS schema_name,
  COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema NOT IN ('INFORMATION_SCHEMA')
GROUP BY 1, 2
ORDER BY 1, 2;
```

**What to look for:**
- Databases and schemas with zero tag coverage (Walk stage gap)
- Inconsistent tag keys across objects (signals no enforced taxonomy)

### 1.9 Recent ACCOUNTADMIN Activity

```sql
-- Query history where ACCOUNTADMIN was the active role
SELECT
  user_name,
  role_name,
  warehouse_name,
  query_type,
  query_text,
  start_time
FROM snowflake.account_usage.query_history
WHERE role_name = 'ACCOUNTADMIN'
  AND start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP)
ORDER BY start_time DESC
LIMIT 100;
```

**What to look for:**
- Routine operational queries running as ACCOUNTADMIN (signals it's being
  used as a workaround)
- Frequency: occasional setup queries are expected, daily operational queries
  are a finding

### 1.10 Service Account Activity Patterns

```sql
-- Query volume by user last 30 days (surfaces active service accounts)
SELECT
  user_name,
  role_name,
  COUNT(*) AS query_count,
  SUM(credits_used_cloud_services) AS cloud_service_credits,
  MIN(start_time) AS first_seen,
  MAX(start_time) AS last_seen
FROM snowflake.account_usage.query_history
WHERE start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP)
GROUP BY user_name, role_name
ORDER BY query_count DESC;
```

**What to look for:**
- Service accounts using roles that don't match their expected workload
- Human users generating high query volumes (may indicate BI tools using
  personal credentials instead of a shared service account)
- Dormant service accounts that still have active grants

---

## Part 2 — Targeted Interview

Conducted after reviewing survey output. Reference specific findings from
Part 1 in each section.

### 2.1 Role History

**For each role identified in the survey that doesn't follow a clear naming
convention:**

- What was this role created for?
- Is it still actively used? By whom?
- What would break if it were removed?

**For any role with ACCOUNTADMIN in its hierarchy:**

- Why was this granted?
- Is there a specific privilege it was a shortcut for?
- Who approved it?

### 2.2 Service Account Mapping

*Goal: map every service account to a single integration and owner.*

| Service account name | Integration / tool | Owner (team or person) | Still active? | Should be migrated? |
|---------------------|-------------------|----------------------|---------------|---------------------|
| | | | Yes / No | Yes / No |

**For any service account that appears to serve multiple integrations:**

- What would break if we split it into per-integration accounts?
- Is there a timeline constraint on that change?

**For dormant service accounts (no activity in 30+ days):**

- Is this intentional (seasonal workload) or should it be deactivated?

### 2.3 Warehouse Usage

**For the warehouse topology identified in the survey:**

- Were the current warehouses set up intentionally or organically?
- Are there workloads that should be isolated but currently share a warehouse?
- Are there warehouses that exist for historical reasons and are no longer
  needed?

**For any warehouse without a resource monitor:**

- Is there a reason no monitor was set up?
- What is the acceptable monthly credit budget per warehouse?

### 2.4 Known Pain Points

*These questions surface the problems the client already knows about.*

- Where does the current environment cause the most friction for the data
  team?
- Are there recurring incidents related to permissions or access? What are
  the typical causes?
- Has cost attribution ever been requested and failed? What was the blocker?
- Is there a "everyone knows we shouldn't but we do anyway" pattern in how
  the environment is used?

### 2.5 Constraints & Dependencies

*These questions surface what cannot be changed immediately.*

- Are there any service accounts or roles that cannot be modified right now
  due to vendor dependencies, active contracts, or in-flight projects?
- Are there any applications that have hardcoded role names or warehouse names
  that would break on rename?
- Is there a change freeze period or deployment window we need to respect?
- Who needs to approve changes to the production environment?

### 2.6 Migration Appetite

- What is the target maturity stage? (Core / Observability / Enforcement)
- Is there a deadline or milestone driving this work?
- How much disruption is acceptable during migration? (e.g. are brief access
  outages acceptable during off-hours?)
- Who on the client side will own the ongoing maintenance after the
  engagement?

---

## Part 3 — Findings Summary

*Completed by the engineer after the survey and interview. This becomes the
basis for the migration plan.*

### Critical Findings
*(Must be addressed before any other work proceeds)*

| Finding | Evidence | Risk | Remediation |
|---------|----------|------|-------------|
| | | | |

### Standard Findings
*(Should be addressed as part of the migration)*

| Finding | Evidence | Priority | Remediation |
|---------|----------|----------|-------------|
| | | | |

### Accepted Deferred Items
*(Known gaps that will not be addressed in this engagement, with documented
reason)*

| Item | Reason deferred | Owner | Target date |
|------|----------------|-------|-------------|
| | | | |

---

## Part 4 — Decisions Log

*Documents every governance design decision made for this specific
environment. References PHILOSOPHY.md for rationale.*

| Decision | Options considered | Choice made | Reason | Constraint | Reference |
|----------|-------------------|-------------|--------|------------|-----------|
| Database structure | Per-source vs shared RAW | | | | PHILOSOPHY.md §Connector Role Philosophy |
| Warehouse topology | Current vs workload-separated | | | | PHILOSOPHY.md §Maturity Model |
| Service account migration order | | | | | PHILOSOPHY.md §Brownfield Compromise |
| Legacy role deprecation approach | Hard cutover vs parallel | Parallel | | | PHILOSOPHY.md §Brownfield Compromise |
| | | | | | |

---

*Flynn Data Services · flynndata.com · Last reviewed: March 2026*

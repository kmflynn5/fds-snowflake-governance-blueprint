# terraform/modules/rbac/functional_roles.tf
#
# Static functional roles: LOADER, TRANSFORMER, ANALYST, FIREFIGHTER, AUDITOR.
#
# IMPORTANT — functional roles are conceptual groupings, not operational assignments.
# Service accounts are NEVER assigned to functional roles directly.
# The operational layer is the connector role (CONN_{NAME}).
#
# See PHILOSOPHY.md §The Connector Role Philosophy:
#   "Functional roles (LOADER, TRANSFORMER, ANALYST) remain in the model as
#    conceptual groupings — useful for auditing, documentation, and communicating
#    intent. They are not operational assignments."

# ---------------------------------------------------------------------------
# Functional roles (conceptual layer)
# ---------------------------------------------------------------------------

resource "snowflake_account_role" "loader" {
  name    = "LOADER"
  comment = "Conceptual role — ingestion workload grouping. See PHILOSOPHY.md §Connector Role Philosophy. Do not assign users or service accounts directly."
}

resource "snowflake_account_role" "transformer" {
  name    = "TRANSFORMER"
  comment = "Conceptual role — transformation workload grouping. See PHILOSOPHY.md §Connector Role Philosophy. Do not assign users or service accounts directly."
}

resource "snowflake_account_role" "analyst" {
  name    = "ANALYST"
  comment = "Conceptual role — analyst and BI workload grouping. See PHILOSOPHY.md §Connector Role Philosophy. Human users assigned here for read-only access."
}

# ---------------------------------------------------------------------------
# FIREFIGHTER — dormant emergency access role
#
# This role has ZERO active user assignments in production.
# Activation process:
#   1. Named approver (see decisions.md §Emergency Access) grants this role to
#      the responding engineer via: GRANT ROLE FIREFIGHTER TO USER {user};
#   2. Engineer performs emergency intervention
#   3. Role is revoked immediately after the incident is resolved
#   4. All FIREFIGHTER sessions are audited via the eval suite
#
# The eval suite asserts zero FIREFIGHTER assignments daily.
# Any assignment outside of an approved incident triggers an alert.
#
# See PHILOSOPHY.md §Core Principles #4:
#   "ACCOUNTADMIN should have zero active user assignments in a production
#    environment. It exists for account-level administration during initial
#    setup and emergency intervention only."
# ---------------------------------------------------------------------------

resource "snowflake_account_role" "firefighter" {
  name    = "FIREFIGHTER"
  comment = "DORMANT — emergency intervention only. Zero active user assignments. Activation requires named approver (see decisions.md). Eval suite asserts zero assignments daily."
}

# FIREFIGHTER sits below SYSADMIN in the hierarchy — it can do anything
# SYSADMIN can do, but activations are auditable and bounded
resource "snowflake_grant_account_role" "firefighter_to_sysadmin" {
  role_name        = snowflake_account_role.firefighter.name
  parent_role_name = "SYSADMIN"
}

# ---------------------------------------------------------------------------
# AUDITOR — read-only role for the eval suite
#
# Used exclusively by the governance eval suite (tests/eval/).
# Scoped to account_usage views only — no access to user databases.
#
# See PHILOSOPHY.md §Core Principles #4 and SPEC.md §Part 5 — Governance Eval Suite
# ---------------------------------------------------------------------------

resource "snowflake_account_role" "auditor" {
  name    = "AUDITOR"
  comment = "Read-only role for the governance eval suite. Access to account_usage metadata only. No user data access. See SPEC.md §Part 5."
}

resource "snowflake_grant_privileges_to_account_role" "auditor_account_usage" {
  account_role_name = snowflake_account_role.auditor.name
  privileges        = ["IMPORTED PRIVILEGES"]

  on_account_object {
    object_type = "DATABASE"
    object_name = "SNOWFLAKE"
  }
}

# ---------------------------------------------------------------------------
# Functional role → SYSADMIN hierarchy
#
# Functional roles inherit from SYSADMIN so that privilege escalation is
# visible in the standard Snowflake role hierarchy view.
# ---------------------------------------------------------------------------

resource "snowflake_grant_account_role" "loader_to_sysadmin" {
  role_name        = snowflake_account_role.loader.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "transformer_to_sysadmin" {
  role_name        = snowflake_account_role.transformer.name
  parent_role_name = "SYSADMIN"
}

resource "snowflake_grant_account_role" "analyst_to_sysadmin" {
  role_name        = snowflake_account_role.analyst.name
  parent_role_name = "SYSADMIN"
}

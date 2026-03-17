# terraform/modules/rbac/functional_roles.tf
#
# Static operational roles: FIREFIGHTER, AUDITOR.
# Dynamic human functional roles: generated from intake/team.yaml via for_each.
#
# NOTE — LOADER, TRANSFORMER, ANALYST are conceptual groupings documented in
# PHILOSOPHY.md §The Connector Role Philosophy. They are intentionally NOT
# created as Snowflake roles — the concepts are expressed through naming
# conventions (CONN_ prefix = loader layer, OBJ_ prefix = object layer,
# human functional role names = analyst/engineer layer) and role comments.
# Role-layer tagging (a `role_layer` tag on each role) is planned for the
# Observability expansion — see PHILOSOPHY.md §Observability Expansion.

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

# ---------------------------------------------------------------------------
# Generated human functional roles (from intake/team.yaml)
#
# One role per persona. All roles granted to SYSADMIN.
# Human users are assigned to these roles — never to connector or object roles.
#
# See PHILOSOPHY.md: "Human users hold functional roles."
# ---------------------------------------------------------------------------

resource "snowflake_account_role" "human_functional" {
  for_each = { for r in var.functional_roles : r.name => r }
  name     = each.key
  comment  = each.value.reason
}

resource "snowflake_grant_account_role" "human_functional_to_sysadmin" {
  for_each         = { for r in var.functional_roles : r.name => r }
  role_name        = snowflake_account_role.human_functional[each.key].name
  parent_role_name = "SYSADMIN"
  depends_on       = [snowflake_account_role.human_functional]
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_warehouse" {
  for_each = {
    for r in var.functional_roles : r.name => r
    if r.warehouse != null && r.warehouse != ""
  }
  account_role_name = snowflake_account_role.human_functional[each.key].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = each.value.warehouse
  }
}

locals {
  # Unique (role, database) pairs — for database USAGE grants
  # distinct() deduplicates before mapping to avoid key collisions when a role
  # has multiple schemas or privileges in the same database.
  functional_db_usage = {
    for pair in distinct([
      for g in var.functional_role_grants :
      { role = g.role, database = g.database }
    ]) :
    "${pair.role}__${pair.database}" => pair
  }

  # Database-level future TABLE grants (schema == null → schemas: ["*"])
  # Filtered to table-level privileges only (SELECT, INSERT).
  # CREATE TABLE and CREATE SCHEMA require separate grant types — see below.
  functional_db_future = {
    for g in var.functional_role_grants :
    "${g.role}__${g.database}__${g.privilege}" => g
    if g.schema == null && contains(["SELECT", "INSERT"], g.privilege)
  }

  # Unique (role, database) pairs where the role needs CREATE TABLE on future schemas
  functional_db_future_create_table = {
    for pair in distinct([
      for g in var.functional_role_grants :
      { role = g.role, database = g.database }
      if g.schema == null && g.privilege == "CREATE TABLE"
    ]) :
    "${pair.role}__${pair.database}" => pair
  }

  # Unique (role, database) pairs where the role needs CREATE SCHEMA on the database
  functional_db_create_schema = {
    for pair in distinct([
      for g in var.functional_role_grants :
      { role = g.role, database = g.database }
      if g.schema == null && g.privilege == "CREATE SCHEMA"
    ]) :
    "${pair.role}__${pair.database}" => pair
  }

  # Database-level future schema USAGE (so new schemas are visible after wildcard grants)
  # distinct() deduplicates before mapping to avoid key collisions when a role
  # has multiple wildcard privileges in the same database.
  functional_wildcard_db_pairs = {
    for pair in distinct([
      for g in var.functional_role_grants :
      { role = g.role, database = g.database }
      if g.schema == null
    ]) :
    "${pair.role}__${pair.database}" => pair
  }

  # Unique (role, database, schema) pairs — for schema USAGE grants
  functional_schema_usage = {
    for g in var.functional_role_grants :
    "${g.role}__${g.database}__${g.schema}" => {
      role     = g.role
      database = g.database
      schema   = g.schema
    }
    if g.schema != null
  }

  # Schema-level future grants (schema != null → named schemas)
  functional_schema_future = {
    for g in var.functional_role_grants :
    "${g.role}__${g.database}__${g.schema}__${g.privilege}" => g
    if g.schema != null
  }
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_db_usage" {
  for_each          = local.functional_db_usage
  account_role_name = snowflake_account_role.human_functional[each.value.role].name
  privileges        = ["USAGE"]
  on_account_object {
    object_type = "DATABASE"
    object_name = each.value.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_db_future" {
  for_each          = local.functional_db_future
  account_role_name = snowflake_account_role.human_functional[each.value.role].name
  privileges        = [each.value.privilege]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = each.value.database
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_db_future_create_table" {
  for_each          = local.functional_db_future_create_table
  account_role_name = snowflake_account_role.human_functional[each.value.role].name
  privileges        = ["CREATE TABLE"]
  on_schema {
    future_schemas_in_database = each.value.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_db_create_schema" {
  for_each          = local.functional_db_create_schema
  account_role_name = snowflake_account_role.human_functional[each.value.role].name
  privileges        = ["CREATE SCHEMA"]
  on_account_object {
    object_type = "DATABASE"
    object_name = each.value.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_future_schema_usage" {
  for_each          = local.functional_wildcard_db_pairs
  account_role_name = snowflake_account_role.human_functional[each.value.role].name
  privileges        = ["USAGE"]
  on_schema {
    future_schemas_in_database = each.value.database
  }
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_schema_usage" {
  for_each          = local.functional_schema_usage
  account_role_name = snowflake_account_role.human_functional[each.value.role].name
  privileges        = ["USAGE"]
  on_schema {
    schema_name = "${each.value.database}.${each.value.schema}"
  }
}

resource "snowflake_grant_privileges_to_account_role" "human_functional_schema_future" {
  for_each          = local.functional_schema_future
  account_role_name = snowflake_account_role.human_functional[each.value.role].name
  privileges        = [each.value.privilege]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "${each.value.database}.${each.value.schema}"
    }
  }
}

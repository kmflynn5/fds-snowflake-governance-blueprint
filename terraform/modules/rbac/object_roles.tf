# terraform/modules/rbac/object_roles.tf
#
# OBJ_{DB}_{TIER} object roles — privilege holders, never assigned to users directly.
#
# Object roles hold actual privileges on databases and schemas.
# Connector roles inherit from object roles.
# Human users never hold object roles directly — they inherit via functional roles.
#
# Pattern: OBJ_{DATABASE}_WRITER or OBJ_{DATABASE}_READER
#
# See PHILOSOPHY.md §Core Principles #2:
#   "No human user ever holds direct object grants. Human users are assigned to
#    functional roles. Functional roles inherit from object roles."
#
# See PHILOSOPHY.md §Least Privilege Standard:
#   "Write access and read access are always separate grants."

# ---------------------------------------------------------------------------
# Object roles
# ---------------------------------------------------------------------------

resource "snowflake_account_role" "object" {
  for_each = var.object_roles

  name    = each.key
  comment = each.value.comment
}

# ---------------------------------------------------------------------------
# Database USAGE grants
#
# Every object role gets USAGE on its database. Without USAGE, no other
# grants in that database are visible to the role.
# ---------------------------------------------------------------------------

resource "snowflake_grant_privileges_to_account_role" "object_database_usage" {
  for_each = var.object_roles

  account_role_name = snowflake_account_role.object[each.key].name
  privileges        = ["USAGE"]

  on_account_object {
    object_type = "DATABASE"
    object_name = each.value.database
  }
}

# ---------------------------------------------------------------------------
# Schema-level privilege grants
#
# Two patterns:
#   1. Specific schemas (where object_roles[*].schemas is non-empty)
#   2. Future grants (applied at database level for "*" schema connectors)
#
# PHILOSOPHY.md §Least Privilege Standard — "future grants: used deliberately
# and documented explicitly ... only at the schema level to a narrowly scoped
# object role."
# ---------------------------------------------------------------------------

# Privilege grants on specific schemas
locals {
  # Flatten object roles with specific schemas into grant targets
  schema_privilege_grants = merge([
    for role_name, role in var.object_roles :
    length(role.schemas) > 0 ? {
      for schema in role.schemas :
      "${role_name}:${role.database}.${schema}" => {
        role_name  = role_name
        database   = role.database
        schema     = schema
        privileges = role.privileges
      }
    } : {}
  ]...)

  # Object roles with "*" schemas get future grants at the database level
  future_grant_roles = {
    for role_name, role in var.object_roles :
    role_name => role
    if length(role.schemas) == 0 && length(role.privileges) > 0
  }

  # Subset of future_grant_roles that have at least one table privilege (SELECT or INSERT).
  # Excludes roles with no applicable privileges to prevent empty privileges argument.
  future_table_grant_roles = {
    for role_name, role in local.future_grant_roles :
    role_name => merge(role, {
      table_privileges = [for p in role.privileges : p if contains(["SELECT", "INSERT"], p)]
    })
    if length([for p in role.privileges : p if contains(["SELECT", "INSERT"], p)]) > 0
  }
}

# Specific schema grants
resource "snowflake_grant_privileges_to_account_role" "object_schema_privileges" {
  for_each = local.schema_privilege_grants

  account_role_name = snowflake_account_role.object[each.value.role_name].name
  privileges        = each.value.privileges

  on_schema {
    schema_name = "${each.value.database}.${each.value.schema}"
  }
}

# Future grants — all tables/views in all schemas of the database
resource "snowflake_grant_privileges_to_account_role" "object_future_table_grants" {
  for_each = local.future_table_grant_roles

  account_role_name = snowflake_account_role.object[each.key].name
  privileges        = each.value.table_privileges

  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_database        = each.value.database
    }
  }
}

# Future grants on views (SELECT only)
resource "snowflake_grant_privileges_to_account_role" "object_future_view_grants" {
  for_each = {
    for k, v in local.future_grant_roles :
    k => v
    if contains(v.privileges, "SELECT")
  }

  account_role_name = snowflake_account_role.object[each.key].name
  privileges        = ["SELECT"]

  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_database        = each.value.database
    }
  }
}

# Future schema USAGE grants (so connector can see new schemas)
resource "snowflake_grant_privileges_to_account_role" "object_future_schema_usage" {
  for_each = local.future_grant_roles

  account_role_name = snowflake_account_role.object[each.key].name
  privileges        = ["USAGE"]

  on_schema {
    future_schemas_in_database = each.value.database
  }
}

# ---------------------------------------------------------------------------
# Extra grants (e.g. Snowpipe CREATE PIPE, MONITOR)
#
# See PHILOSOPHY.md §Core Principles #9:
#   "Storage integrations are never granted to functional roles."
# ---------------------------------------------------------------------------

locals {
  extra_grant_roles = {
    for role_name, role in var.object_roles :
    role_name => role
    if length(role.extra_grants) > 0
  }
}

resource "snowflake_grant_privileges_to_account_role" "object_extra_grants" {
  for_each = local.extra_grant_roles

  account_role_name = snowflake_account_role.object[each.key].name
  privileges        = each.value.extra_grants

  on_schema {
    # Extra grants scoped to the full database — Snowpipe CREATE PIPE needs schema-level
    all_schemas_in_database = each.value.database
  }
}

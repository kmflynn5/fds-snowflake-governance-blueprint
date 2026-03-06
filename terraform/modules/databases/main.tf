# terraform/modules/databases/main.tf
#
# Creates Snowflake databases and schemas derived from connectors.yaml.
# Each connector's target_db produces a database. Schemas are created where
# target_schemas is a specific list (not "*").
#
# "*" schemas mean the connector manages schema creation dynamically (e.g. Fivetran
# creates schemas per source table, dbt creates schemas per environment).
#
# References:
#   PHILOSOPHY.md §Least Privilege Standard — "at the database level: service accounts
#     are scoped to the specific database their workload requires"
#   SPEC.md §Part 3 — database isolation per connector

# ---------------------------------------------------------------------------
# Databases
# ---------------------------------------------------------------------------

resource "snowflake_database" "this" {
  for_each = var.databases

  name    = each.key
  comment = each.value.comment
}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

# Only creates schemas for connectors that declare specific target schemas.
# Connectors with target_schemas: ["*"] manage their own schemas dynamically.
locals {
  # Flatten databases → schemas into a map keyed by "DB.SCHEMA"
  schema_entries = merge([
    for db_name, db in var.databases : {
      for schema in db.schemas :
      "${db_name}.${schema}" => {
        database = db_name
        schema   = schema
      }
    }
  ]...)
}

resource "snowflake_schema" "this" {
  for_each = local.schema_entries

  database = snowflake_database.this[each.value.database].name
  name     = each.value.schema
}

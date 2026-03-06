output "database_names" {
  description = "Map of database name → snowflake database name"
  value       = { for k, v in snowflake_database.this : k => v.name }
}

output "schema_fqns" {
  description = "Map of 'DB.SCHEMA' key → fully qualified schema name"
  value = {
    for k, v in snowflake_schema.this :
    k => "${v.database}.${v.name}"
  }
}

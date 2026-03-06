output "connector_role_names" {
  description = "Map of connector role key → Snowflake role name"
  value       = { for k, v in snowflake_account_role.connector : k => v.name }
}

output "object_role_names" {
  description = "Map of object role key → Snowflake role name"
  value       = { for k, v in snowflake_account_role.object : k => v.name }
}

output "functional_role_names" {
  description = "Map of functional role name → Snowflake role name"
  value = {
    LOADER      = snowflake_account_role.loader.name
    TRANSFORMER = snowflake_account_role.transformer.name
    ANALYST     = snowflake_account_role.analyst.name
    FIREFIGHTER = snowflake_account_role.firefighter.name
    AUDITOR     = snowflake_account_role.auditor.name
  }
}

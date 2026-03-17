output "connector_role_names" {
  description = "Map of connector role key → Snowflake role name"
  value       = { for k, v in snowflake_account_role.connector : k => v.name }
}

output "object_role_names" {
  description = "Map of object role key → Snowflake role name"
  value       = { for k, v in snowflake_account_role.object : k => v.name }
}

output "functional_role_names" {
  description = "Map of human functional role name → Snowflake role name (from intake/team.yaml)"
  value       = { for k, v in snowflake_account_role.human_functional : k => v.name }
}

output "system_role_names" {
  description = "Map of system-managed operational roles (FIREFIGHTER, AUDITOR)"
  value = {
    FIREFIGHTER = snowflake_account_role.firefighter.name
    AUDITOR     = snowflake_account_role.auditor.name
  }
}

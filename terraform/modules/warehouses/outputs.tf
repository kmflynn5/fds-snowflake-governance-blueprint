output "warehouse_names" {
  description = "Map of warehouse key → full Snowflake warehouse name (WH_{key})"
  value       = { for k, v in snowflake_warehouse.this : k => v.name }
}

output "resource_monitor_names" {
  description = "Map of warehouse key → resource monitor name"
  value       = { for k, v in snowflake_resource_monitor.this : k => v.name }
}

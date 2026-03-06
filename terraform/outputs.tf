output "database_names" {
  description = "All created database names"
  value       = module.databases.database_names
}

output "schema_fqns" {
  description = "All created schema FQNs"
  value       = module.databases.schema_fqns
}

output "warehouse_names" {
  description = "All created warehouse names"
  value       = module.warehouses.warehouse_names
}

output "resource_monitor_names" {
  description = "All created resource monitor names"
  value       = module.warehouses.resource_monitor_names
}

output "connector_role_names" {
  description = "All created connector role names"
  value       = module.rbac.connector_role_names
}

output "object_role_names" {
  description = "All created object role names"
  value       = module.rbac.object_role_names
}

output "functional_role_names" {
  description = "Static functional role names"
  value       = module.rbac.functional_role_names
}

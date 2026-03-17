# terraform/main.tf
#
# Root module — wires databases, warehouses, and RBAC modules together.
#
# Configuration is driven by generated .auto.tfvars.json files:
#   terraform/databases.auto.tfvars.json
#   terraform/warehouses.auto.tfvars.json
#   terraform/rbac.auto.tfvars.json
#
# To update infrastructure:
#   1. Edit intake/connectors.yaml
#   2. Run: uv run scripts/generate_tf.py
#   3. Run: terraform plan && terraform apply
#
# Never edit the generated .auto.tfvars.json files directly.
# Never edit HCL modules to accommodate a single client's config.
#
# References:
#   PHILOSOPHY.md — governance principles
#   SPEC.md §Build Sequence — module ordering rationale

module "databases" {
  source = "./modules/databases"

  databases   = var.databases
  environment = var.environment
}

module "warehouses" {
  source = "./modules/warehouses"

  warehouses                    = var.warehouses
  resource_monitor_notify_users = var.resource_monitor_notify_users
  environment                   = var.environment
}

module "rbac" {
  source = "./modules/rbac"

  connector_roles                 = var.connector_roles
  object_roles                    = var.object_roles
  connector_to_object_role_grants = var.connector_to_object_role_grants
  connector_to_warehouse_grants   = var.connector_to_warehouse_grants
  connector_type_mapping          = var.connector_type_mapping
  databases                       = module.databases.database_names
  warehouses                      = module.warehouses.warehouse_names
  functional_roles                = var.functional_roles
  functional_role_grants          = var.functional_role_grants

  depends_on = [module.databases, module.warehouses]
}

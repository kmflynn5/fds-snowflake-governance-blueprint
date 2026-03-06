variable "connector_roles" {
  description = "Map of connector role name → role config. Derived from generate_tf.py."
  type = map(object({
    name      = string
    reason    = string
    type      = string
    warehouse = string
  }))
}

variable "object_roles" {
  description = "Map of object role name → role config. Derived from generate_tf.py."
  type = map(object({
    database     = string
    tier         = string
    privileges   = list(string)
    extra_grants = list(string)
    schemas      = list(string)
    comment      = string
  }))
}

variable "connector_to_object_role_grants" {
  description = "List of {connector_role, object_role} pairs. Derived from generate_tf.py."
  type = list(object({
    connector_role = string
    object_role    = string
  }))
}

variable "connector_to_warehouse_grants" {
  description = "List of {connector_role, warehouse} pairs. Derived from generate_tf.py."
  type = list(object({
    connector_role = string
    warehouse      = string
  }))
}

variable "connector_type_mapping" {
  description = "Map of connector role name → functional type (etl, orchestrator, transformer, bi_tool, etc.)."
  type        = map(string)
}

variable "databases" {
  description = "Map of database names (from databases module outputs). Used for USAGE grants."
  type        = map(string)
  default     = {}
}

variable "warehouses" {
  description = "Map of warehouse keys → names (from warehouses module outputs). Used for USAGE grants."
  type        = map(string)
  default     = {}
}

# terraform/modules/warehouses/resource_monitors.tf
#
# Attaches a resource monitor to every warehouse.
# At Crawl stage, every warehouse must have a monitor — unmonitored warehouses
# are a critical finding in the brownfield audit.
#
# Default thresholds (override per-warehouse in connectors.yaml):
#   notify_triggers:  75% of monthly credit quota
#   suspend_triggers: 100% of monthly credit quota
#
# References:
#   PHILOSOPHY.md §Maturity Model — Crawl (resource monitors required at Crawl)
#   SPEC.md §Part 3 — Resource Monitor Defaults

resource "snowflake_resource_monitor" "this" {
  for_each = var.warehouses

  name         = "RM_WH_${each.key}"
  credit_quota = each.value.monthly_credit_quota

  # Notify at 75% of monthly budget
  notify_triggers = [each.value.notify_at_percentage]

  # Suspend at 100% of monthly budget
  suspend_trigger = each.value.suspend_at_percentage

  notify_users = var.resource_monitor_notify_users
}

# Attach each resource monitor to its warehouse
resource "snowflake_warehouse" "monitored" {
  for_each = var.warehouses

  name             = snowflake_warehouse.this[each.key].name
  resource_monitor = snowflake_resource_monitor.this[each.key].name

  # Preserve all settings from the base warehouse resource
  warehouse_size = each.value.size
  auto_suspend   = each.value.auto_suspend_seconds
  auto_resume    = each.value.auto_resume
  comment        = each.value.comment

  depends_on = [snowflake_warehouse.this, snowflake_resource_monitor.this]

  lifecycle {
    ignore_changes = [warehouse_size, auto_suspend, auto_resume, comment]
  }
}

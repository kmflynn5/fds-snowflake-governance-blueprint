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
#   PHILOSOPHY.md §Maturity Model — Core (resource monitors required at Core)
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

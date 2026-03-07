# terraform/modules/warehouses/main.tf
#
# Creates Snowflake warehouses derived from connectors.yaml warehouse fields.
# Each unique warehouse value in connectors.yaml becomes a WH_{NAME} warehouse.
#
# Default configuration:
#   - Size: XSMALL (right-size after observing actual usage)
#   - Auto-suspend: 300 seconds (5 minutes)
#   - Auto-resume: true (transparent to tools)
#
# References:
#   PHILOSOPHY.md §The Warehouse Isolation Standard
#   PHILOSOPHY.md §Maturity Model — Crawl (resource monitors required at Crawl)
#   SPEC.md §Part 3 — Default Warehouse Topology

resource "snowflake_warehouse" "this" {
  for_each = var.warehouses

  name             = "WH_${each.key}"
  warehouse_size   = each.value.size
  auto_suspend     = each.value.auto_suspend_seconds
  auto_resume      = each.value.auto_resume
  resource_monitor = snowflake_resource_monitor.this[each.key].name
  comment          = each.value.comment
}

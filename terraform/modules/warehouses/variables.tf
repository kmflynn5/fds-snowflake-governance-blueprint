variable "warehouses" {
  description = "Map of warehouses to create, derived from generate_tf.py. Key is the warehouse name (without WH_ prefix)."
  type = map(object({
    size                  = string
    auto_suspend_seconds  = number
    auto_resume           = bool
    monthly_credit_quota  = number
    notify_at_percentage  = number
    suspend_at_percentage = number
    comment               = string
  }))
}

variable "resource_monitor_notify_users" {
  description = "Snowflake usernames to notify when resource monitor thresholds are hit. Must be ACCOUNTADMIN holders."
  type        = list(string)
  default     = []
}

variable "environment" {
  description = "Environment tag value applied to all resources"
  type        = string
  default     = "prod"
}

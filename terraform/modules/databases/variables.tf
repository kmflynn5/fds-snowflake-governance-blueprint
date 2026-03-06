variable "databases" {
  description = "Map of databases to create, derived from generate_tf.py. Key is the database name."
  type = map(object({
    schemas = list(string)
    comment = string
  }))
}

variable "environment" {
  description = "Environment tag value applied to all resources (prod, staging, dev)"
  type        = string
  default     = "prod"
}

# snowflakedb/snowflake provider — all auth via environment variables.
# The provider reads these automatically; no explicit HCL arguments needed:
#   SNOWFLAKE_ACCOUNT           — account identifier (e.g. xy12345.us-east-1)
#   SNOWFLAKE_USER              — Terraform service account username
#   SNOWFLAKE_PRIVATE_KEY_PATH  — path to RSA private key file
#   SNOWFLAKE_ROLE              — set to SYSADMIN for infrastructure operations
#
# See: docs/PHILOSOPHY.md §Core Principles #8 (key-pair auth)

provider "snowflake" {}

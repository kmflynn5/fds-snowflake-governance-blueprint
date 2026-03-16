# snowflakedb/snowflake provider — all auth via environment variables.
# The provider reads these automatically; no explicit HCL arguments needed:
#   SNOWFLAKE_ORGANIZATION_NAME — org portion of account identifier (e.g. MUQRXDZ)
#   SNOWFLAKE_ACCOUNT_NAME      — account portion of account identifier (e.g. ZCC08506)
#   SNOWFLAKE_USER              — Terraform service account username
#   SNOWFLAKE_PRIVATE_KEY_PATH  — path to RSA private key file
#   SNOWFLAKE_ROLE              — role for infrastructure operations (TF_SYSADMIN)
#
# See: docs/PHILOSOPHY.md §Core Principles #8 (key-pair auth)

provider "snowflake" {}

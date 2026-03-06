# snowflake-labs/snowflake provider configuration
# All credentials are sourced from environment variables — never hardcoded.
#
# Required environment variables:
#   SNOWFLAKE_ACCOUNT    — account identifier (e.g. xy12345.us-east-1)
#   SNOWFLAKE_USER       — username of the Terraform service account
#   SNOWFLAKE_PRIVATE_KEY_PATH — path to RSA private key (key-pair auth)
#
# See: docs/PHILOSOPHY.md §Core Principles #8 (key-pair auth)
# See: terraform/terraform.tfvars.example for full variable reference

provider "snowflake" {
  account  = var.snowflake_account
  username = var.snowflake_user
  role     = "SYSADMIN"

  private_key_path = var.snowflake_private_key_path
}

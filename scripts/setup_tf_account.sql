-- scripts/setup_tf_account.sql
-- Run as ACCOUNTADMIN to create the Terraform service account.
-- This is a ONE-TIME setup step before running `terraform apply`.
--
-- DO NOT run this via copy/paste — use the substitution command below so the
-- RSA public key is injected automatically from your local keyfile:
--
--   PUB_KEY=$(grep -v "^-----" ~/.snowflake/tf_rsa_key.pub | tr -d '\n')
--   sed "s|<PASTE_PUBLIC_KEY_HERE>|$PUB_KEY|" scripts/setup_tf_account.sql \
--     | snow sql --stdin -c admin
--
-- After the trial, tear down with:
--   snow sql -q "DROP USER IF EXISTS TF_SYSADMIN; DROP ROLE IF EXISTS TF_SYSADMIN;" -c admin

USE ROLE ACCOUNTADMIN;

-- Terraform automation role — inherits SYSADMIN + SECURITYADMIN for full infra scope
-- (SECURITYADMIN is required for CREATE ROLE and GRANT ROLE operations)
CREATE ROLE IF NOT EXISTS TF_SYSADMIN
  COMMENT = 'Terraform automation role — infrastructure apply only';

GRANT ROLE SYSADMIN      TO ROLE TF_SYSADMIN;
GRANT ROLE SECURITYADMIN TO ROLE TF_SYSADMIN;
GRANT ROLE ACCOUNTADMIN  TO ROLE TF_SYSADMIN;  -- required for CREATE RESOURCE MONITOR

CREATE USER IF NOT EXISTS TF_SYSADMIN
  DEFAULT_ROLE      = TF_SYSADMIN
  DEFAULT_WAREHOUSE = NULL
  RSA_PUBLIC_KEY    = 'MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA6LwbRuNrYT3fSDaAHUC3JyFxXYwEb9+tC+B5xHjp6kZpir4Itmamh3zIqkCVpnW+10hd+qSqjyggUQyl/AhvkBXiWhs51fBuA+gR7Cfwb2ZpLTfk8NHKnVzT6F/n46/6Zd/h5JogHYWCqiFog1659kwaQp3I0x6RdELiG8yCCzdSscwg8ZglHj8WEyGlH5sr4HuUedAJhrlKFbdQgFquSlCUEqxKGEztMAUeeOkZbNWumKPLFpJlVm/5ZTGZgqJwL6Vd44a7oIIDyvrsP3wP4Akm8Vhm4R0iaQ4z89iS3AMWF0JXtPMllOGvo5Ptm1pCyh9uq5XsB1gPTiV4nfuU/QIDAQAB'
  COMMENT           = 'Terraform service account — key-pair auth only, no password';

GRANT ROLE TF_SYSADMIN TO USER TF_SYSADMIN;

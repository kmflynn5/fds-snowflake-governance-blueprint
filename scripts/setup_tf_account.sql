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

-- Terraform automation role.
-- Role grants and why each is required:
--   SYSADMIN      — create databases, warehouses
--   SECURITYADMIN — create roles, manage grants
--   ACCOUNTADMIN  — CREATE RESOURCE MONITOR (cannot be delegated to lower roles)
--
-- TRADEOFF: TF_SYSADMIN holds ACCOUNTADMIN. Risk is low — no password, no
-- interactive login — but this violates least-privilege for a service account.
--
-- For tighter security after initial apply, revoke ACCOUNTADMIN and re-grant
-- only when resource monitor config is changing:
--   snow sql -q "REVOKE ROLE ACCOUNTADMIN FROM ROLE TF_SYSADMIN;" -c admin
--
-- TODO (Walk stage): replace manual grant/revoke with a second Terraform
-- provider alias scoped to ACCOUNTADMIN for resource monitor resources only.
-- See: docs/GREENFIELD_TESTING_PLAN.md §Known Limitations — TF_SYSADMIN
CREATE ROLE IF NOT EXISTS TF_SYSADMIN
  COMMENT = 'Terraform automation role — infrastructure apply only';

GRANT ROLE SYSADMIN      TO ROLE TF_SYSADMIN;
GRANT ROLE SECURITYADMIN TO ROLE TF_SYSADMIN;
GRANT ROLE ACCOUNTADMIN  TO ROLE TF_SYSADMIN;

CREATE USER IF NOT EXISTS TF_SYSADMIN
  DEFAULT_ROLE      = TF_SYSADMIN
  DEFAULT_WAREHOUSE = NULL
  RSA_PUBLIC_KEY    = '<PASTE_PUBLIC_KEY_HERE>'
  COMMENT           = 'Terraform service account — key-pair auth only, no password';

GRANT ROLE TF_SYSADMIN TO USER TF_SYSADMIN;

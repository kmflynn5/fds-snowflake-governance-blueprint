-- scripts/audit_setup.sql
-- Run this as SECURITYADMIN (or ACCOUNTADMIN if SECURITYADMIN is unavailable).
-- Creates a temporary read-only audit role + user scoped to account_usage views only.
--
-- This is a ONE-TIME setup step before running scripts/audit.py.
-- Estimated time: 5 minutes.
--
-- After the audit is complete, run scripts/audit_teardown.sql to remove all access.
-- See: scripts/AUDIT_SETUP.md for full step-by-step instructions.

-- Step 1: Create the temporary audit role
CREATE ROLE IF NOT EXISTS FDS_AUDITOR_TEMP
  COMMENT = 'Temporary role for Flynn Data Services governance audit. Safe to drop after audit is complete.';

-- Step 2: Grant read access to account_usage views
-- IMPORTED PRIVILEGES on the SNOWFLAKE database gives read-only access to
-- account_usage metadata views (roles, grants, warehouses, query history stats).
-- FDS_AUDITOR_TEMP has ZERO access to any user tables or databases.
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE FDS_AUDITOR_TEMP;

-- Step 3: Grant USAGE on a warehouse (required to execute queries, XS is fine)
-- Replace <WH_NAME> with the smallest available warehouse in your environment.
GRANT USAGE ON WAREHOUSE <WH_NAME> TO ROLE FDS_AUDITOR_TEMP;

-- Step 4: Create the temporary audit user with key-pair auth (no password)
-- Replace <paste public key from uv run scripts/audit.py keygen> with the output
-- of: uv run scripts/audit.py keygen
-- See: scripts/AUDIT_SETUP.md Step 1 for keygen instructions.
CREATE USER IF NOT EXISTS FDS_AUDITOR_USER
  DEFAULT_ROLE = FDS_AUDITOR_TEMP
  DEFAULT_WAREHOUSE = <WH_NAME>
  RSA_PUBLIC_KEY = '<paste public key from uv run scripts/audit.py keygen>'
  COMMENT = 'Temporary user for Flynn Data Services governance audit. Safe to drop after audit.';

-- Step 5: Assign the role to the user
GRANT ROLE FDS_AUDITOR_TEMP TO USER FDS_AUDITOR_USER;

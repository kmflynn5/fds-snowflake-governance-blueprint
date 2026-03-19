-- scripts/brownfield_teardown.sql
-- Brownfield testing — revert all injected governance violations.
-- Run as ACCOUNTADMIN in Snowsight AFTER the audit is complete.
--
-- See docs/BROWNFIELD_TESTING_PLAN.md for the full runbook.

USE ROLE ACCOUNTADMIN;

-- Revoke all injected role grants from the test user
REVOKE ROLE ACCOUNTADMIN       FROM USER USER_BF_TEST;
REVOKE ROLE OBJ_RAW_FIVETRAN_WRITER FROM USER USER_BF_TEST;
REVOKE ROLE FIREFIGHTER        FROM USER USER_BF_TEST;
REVOKE ROLE BREAK_GLASS_TEMP   FROM USER USER_BF_TEST;

-- Revoke direct object privilege granted to the test user
REVOKE USAGE ON DATABASE RAW_FIVETRAN FROM USER USER_BF_TEST;

-- Drop all test artifacts
DROP USER      IF EXISTS USER_BF_TEST;
DROP ROLE      IF EXISTS LEGACY_LOADER;
DROP ROLE      IF EXISTS BREAK_GLASS_TEMP;
DROP WAREHOUSE IF EXISTS WH_BROWNFIELD_UNMONITORED;

-- Verify FIREFIGHTER is clean — expected: empty resultset (or only TF_SYSADMIN
-- setup grants if those were added during Terraform provisioning)
SHOW GRANTS OF ROLE FIREFIGHTER;

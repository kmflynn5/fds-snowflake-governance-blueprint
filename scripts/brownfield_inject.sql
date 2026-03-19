-- scripts/brownfield_inject.sql
-- Brownfield testing — inject governance violations for audit validation.
-- Run as ACCOUNTADMIN in Snowsight (or via SnowSQL).
-- After injection, run the full audit pipeline; then run brownfield_teardown.sql.
--
-- See docs/BROWNFIELD_TESTING_PLAN.md for the full runbook.

USE ROLE ACCOUNTADMIN;

-- 1. Create a test user to receive bad grants.
--    TYPE = SERVICE so it is excluded from MFA-required user checks,
--    but it IS a named user that should not hold privileged roles.
CREATE USER IF NOT EXISTS USER_BF_TEST
  TYPE = SERVICE
  COMMENT = 'BROWNFIELD TEST ARTIFACT — drop after brownfield audit test';

-- 2. Grant ACCOUNTADMIN directly to the test user.
--    Expected finding → 1.2 accountadmin_users: CRITICAL
GRANT ROLE ACCOUNTADMIN TO USER USER_BF_TEST;

-- 3. Grant an OBJ_ role directly to the test user (human on object role).
--    Expected finding → 1.3 human_role_assignments: STANDARD
GRANT ROLE OBJ_RAW_FIVETRAN_WRITER TO USER USER_BF_TEST;

-- 4. Grant a direct object privilege to the test user (bypasses role hierarchy).
--    Expected finding → 1.3 direct_grants: CRITICAL
GRANT USAGE ON DATABASE RAW_FIVETRAN TO USER USER_BF_TEST;

-- 5. Create an ad-hoc role with a non-standard name.
--    Expected finding → 1.1 roles: STANDARD (ad-hoc naming)
CREATE ROLE IF NOT EXISTS LEGACY_LOADER
  COMMENT = 'BROWNFIELD TEST ARTIFACT — drop after brownfield audit test';

-- 6a. Assign FIREFIGHTER directly to the test user (exact framework role name).
--     Expected finding → 1.1 grants_to_roles: CRITICAL (break-glass assigned)
GRANT ROLE FIREFIGHTER TO USER USER_BF_TEST;

-- 6b. Create a break-glass variant role and assign it too (tests pattern matching).
--     Expected finding → 1.1 grants_to_roles: CRITICAL (break-glass pattern)
CREATE ROLE IF NOT EXISTS BREAK_GLASS_TEMP
  COMMENT = 'BROWNFIELD TEST ARTIFACT — drop after brownfield audit test';
GRANT ROLE BREAK_GLASS_TEMP TO USER USER_BF_TEST;

-- 7. Create an unmonitored warehouse (deliberately no resource monitor attached).
--    Expected finding → 1.5 unmonitored_warehouses: CRITICAL
CREATE WAREHOUSE IF NOT EXISTS WH_BROWNFIELD_UNMONITORED
  WAREHOUSE_SIZE = XSMALL
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  COMMENT = 'BROWNFIELD TEST ARTIFACT — drop after brownfield audit test';
-- Deliberately do NOT create a resource monitor for this warehouse.
-- Grant USAGE to the auditor role so SHOW WAREHOUSES includes it.
GRANT USAGE ON WAREHOUSE WH_BROWNFIELD_UNMONITORED TO ROLE FDS_AUDITOR_TEMP;

-- 8. Operational query executed as ACCOUNTADMIN.
--    Populates SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY with an AA SELECT.
--    Expected finding → 1.7 accountadmin_queries: CRITICAL
--    NOTE: query_history has 45–180 min latency; run audit after that window.
USE ROLE ACCOUNTADMIN;
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.USERS;

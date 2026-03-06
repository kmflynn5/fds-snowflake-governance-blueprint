-- scripts/audit_teardown.sql
-- Run after the audit is complete to remove all temporary access.
--
-- Run this as SECURITYADMIN (or ACCOUNTADMIN if SECURITYADMIN is unavailable).
-- Estimated time: 2 minutes.

DROP USER IF EXISTS FDS_AUDITOR_USER;
DROP ROLE IF EXISTS FDS_AUDITOR_TEMP;

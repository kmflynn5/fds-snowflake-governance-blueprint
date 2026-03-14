<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Expansion Pack: Enforcement

*Flynn Data Services — Additive expansion on top of Core*

## What It Includes

- **Snowflake tag policies** — object-level tag policies that block untagged object creation
  at the database level before it happens. Governance violations are prevented and logged,
  not just detected after the fact.
- **FIREFIGHTER activation logging** — FIREFIGHTER role activation triggers an automated
  audit log entry within 60 seconds, captured in `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`
  and surfaced as an incident alert.
- **GitHub Actions RBAC policy check** — an updated GitHub Actions workflow that compares
  the PR diff against defined RBAC policies and blocks merge if violations are detected.
  No RBAC change merges without a passing policy check.

## When to Adopt

This expansion is right for larger teams operating across multiple business units,
environments subject to regulatory requirements (SOC 2, HIPAA, GDPR), or any team where
the Observability expansion has surfaced persistent drift that manual remediation is not
resolving. If you find yourself reviewing the same types of violations week after week,
enforcement is the answer.

This expansion can be adopted without Observability, but the Evidence dashboard from
Observability provides useful context for tuning enforcement policies before they go live.

## Done Criteria

- [ ] Tag policies active in Snowflake — untagged object creation is blocked, not just flagged
- [ ] FIREFIGHTER activation is logged as an audit event within 60 seconds of role assignment
- [ ] Pull requests that violate defined RBAC policies are blocked from merging
- [ ] Zero tolerance: no RBAC changes can be applied outside the PR workflow

---

*Flynn Data Services · flynndata.com · See also: [EXPANSION_OBSERVABILITY.md](EXPANSION_OBSERVABILITY.md)*

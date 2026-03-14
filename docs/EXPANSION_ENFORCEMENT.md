<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->
# Expansion Pack: Enforcement

*Flynn Data Services — Additive expansion on top of Core*

## What It Includes

Enforcement operates at two layers: mechanisms native to Snowflake that prevent or detect
violations regardless of how they occur, and CI/CD mechanisms that catch violations before
they reach Snowflake.

### Snowflake-Native Enforcement

- **Tag policies** — Snowflake-native tag policies that block untagged object creation at
  the database level. Governance violations are prevented at the engine level, not detected
  after the fact. No external tooling required — enforcement persists even if CI/CD is
  bypassed or unavailable.

- **FIREFIGHTER activation alert** — a Snowflake Alert evaluating `QUERY_HISTORY` on a
  60-second schedule. Any `USE ROLE FIREFIGHTER` statement or any query executed by the
  FIREFIGHTER role triggers a notification action that posts to the incident channel. This
  runs inside Snowflake itself — it catches activations from Terraform, the console,
  SnowSQL, or any other entry point.

- **RBAC hierarchy as implicit enforcement** — the Core framework already prevents most
  unauthorized changes by design. Human users hold functional roles (ANALYST, TRANSFORMER)
  without CREATE or GRANT privileges. Service accounts hold connector roles scoped to
  specific databases. If your role can't create objects, you can't create untagged objects.
  This expansion verifies and monitors that constraint rather than duplicating it.

### CI/CD Enforcement

- **RBAC policy check on PR** — a GitHub Actions workflow that compares the PR diff against
  defined RBAC policies and blocks merge if violations are detected. No RBAC change merges
  without a passing policy check.

- **Plan-on-merge drift detection** — every merge to `main` triggers `terraform plan`. If
  the plan shows unexpected changes (resources not attributable to the current PR), the
  pipeline flags it as a drift incident. This catches the case where someone made a manual
  change in Snowflake that Terraform now wants to correct.

## When to Adopt

This expansion is right for teams operating across multiple business units, environments
subject to regulatory requirements (SOC 2, HIPAA, GDPR), or any team where the
Observability expansion has surfaced persistent drift that manual remediation is not
resolving. If you find yourself reviewing the same types of violations week after week,
enforcement is the answer.

This expansion can be adopted without Observability, but the Evidence dashboard from
Observability provides useful context for tuning enforcement policies before they go live.
Recommended sequence: run Observability for 2–4 weeks to establish a baseline, then enable
enforcement once you understand your team's typical drift patterns.

## Done Criteria

### Setup (verified once during deployment)

- [ ] Snowflake tag policies active — untagged object creation is blocked, not just flagged
- [ ] Snowflake Alert created for FIREFIGHTER role activation on a 60-second schedule
- [ ] Alert notification action configured and verified (Slack webhook or PagerDuty)
- [ ] GitHub Actions RBAC policy check running on all PRs to `main`
- [ ] Plan-on-merge workflow running and producing drift reports

### Operational (continuously true)

- [ ] FIREFIGHTER activation detected and alerted within 60 seconds, regardless of entry point
- [ ] No RBAC pull request merges without a passing policy check
- [ ] RBAC changes applied outside the PR workflow are detected within one `terraform plan`
  cycle and treated as incidents
- [ ] Tag policy violations are blocked at object creation — zero untagged objects enter
  the environment after enforcement is enabled
- [ ] ACCOUNTADMIN remains at zero active assignments

---

*Flynn Data Services · flynndata.com · See also: [EXPANSION_OBSERVABILITY.md](EXPANSION_OBSERVABILITY.md)*

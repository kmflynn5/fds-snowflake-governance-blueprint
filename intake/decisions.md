# Governance Decision Log
*Flynn Data Services — Generated during intake*

This document records every governance design decision made for this environment.
Every decision references PHILOSOPHY.md for rationale. This file is committed to
the repo and updated as the environment evolves.

It is an audit trail and onboarding document — not consumed by Terraform.

---

## Environment Context

| Field | Value |
|-------|-------|
| Client | ___________________ |
| Environment purpose | ___________________ |
| Intake date | ___________________ |
| Engineer | ___________________ |
| Maturity target | Crawl / Walk / Run |

---

## Decisions

| Decision | Options considered | Choice made | Reason | Reference |
|----------|-------------------|-------------|--------|-----------|
| Database structure | Per-source vs shared RAW | Per-source (RAW_FIVETRAN, RAW_AIRFLOW, EVENTS, ANALYTICS, MARTS) | Stronger isolation — a compromised Fivetran credential has no visibility into Airflow schemas or event streams | PHILOSOPHY.md §Connector Role Philosophy |
| Warehouse topology | Single shared vs workload-separated | Workload-separated (WH_INGEST, WH_TRANSFORM, WH_ANALYTICS) | Noisy neighbor rule — transformation jobs competing with analyst queries degrades both | PHILOSOPHY.md §The Warehouse Isolation Standard |
| Maturity target | Crawl / Walk / Run | Crawl | Structure first, enforcement second — Walk enforcement added once baseline is stable | PHILOSOPHY.md §The Maturity Model |
| Connector role pattern | Functional roles only vs connector layer | Connector layer (CONN_{NAME}) | LOADER is too broad — each integration gets its own scoped role | PHILOSOPHY.md §The Connector Role Philosophy |
| Service account auth | Password vs key-pair | Key-pair (RSA) | Passwords cannot be audited for access; key-pair auth is the baseline for all service accounts | PHILOSOPHY.md §Core Principles #8 |
| FIREFIGHTER activation | Self-service vs named approvers | Named approvers (see Emergency Access below) | Dormant role must have an explicit approval gate — self-service defeats the purpose | PHILOSOPHY.md §Core Principles #4 |

---

## Emergency Access (FIREFIGHTER)

| Name | Title | Contact |
|------|-------|---------|
| ___________________ | ___________________ | ___________________ |

**Notification process:** ___________________

**Deactivation SLA:** ___________________ (e.g. "Same day / Within 24 hours")

---

## Brownfield Migration Notes

*(Complete this section for brownfield engagements only)*

### Critical Findings Addressed

| Finding | Remediation | Status |
|---------|-------------|--------|
| | | |

### Accepted Technical Debt

| Item | Reason | Owner | Target date |
|------|--------|-------|-------------|
| | | | |

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| | Initial intake | |

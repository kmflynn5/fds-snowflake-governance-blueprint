# Changelog

All notable changes to this template will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Version tags follow [Semantic Versioning](https://semver.org/).

When forking for a client engagement, note the tag you forked from in
`intake/decisions.md`. When pulling upstream improvements into an existing
fork, review this file to understand what changed and whether it affects
your client's governance decisions.

---

## [Unreleased]

### Changed
- Renamed maturity model: Crawl/Walk/Run → Core + Expansion Packs (Observability, Enforcement)
- `enforcement_stage` enum updated: `crawl|walk|run` → `core|observability|enforcement`
- README restructured as evaluator-facing artifact; operational steps moved to `docs/QUICK_START.md`
- Added upstream improvement guidance to Forking section

### Added
- `docs/EXPANSION_OBSERVABILITY.md` — Observability expansion pack definition and done criteria
- `docs/EXPANSION_ENFORCEMENT.md` — Enforcement expansion pack definition and done criteria
- `docs/QUICK_START.md` — full setup steps for greenfield and brownfield engagements

### Removed
- `docs/SPEC.md` — archived; was the original init prompt, not living documentation

---

## [0.1.0] — 2026-03-14

Initial working release. Core stage fully implemented and trial-validated.

### Added
- `intake/connectors.yaml` + `intake/tags.yaml` schema and example config
- `scripts/intake_interview.py` — interactive intake CLI (greenfield + brownfield modes)
- `scripts/generate_tf.py` — codegen: derives databases, warehouses, RBAC from YAML
- `scripts/audit.py` — brownfield audit across 8 survey sections, produces `gap_report.md`
- `terraform/modules/rbac/` — connector roles, object roles, functional roles via `for_each`
- `terraform/modules/warehouses/` — warehouses + resource monitors
- `terraform/modules/databases/` — databases + schemas
- `.claude/skills/intake-greenfield.md` + `intake-review.md` — Claude Code skill shortcuts
- `docs/PHILOSOPHY.md` — governance principles
- `docs/GREENFIELD_TESTING_PLAN.md` — end-to-end trial run guide
- 52 unit tests across codegen, audit, and intake CLI

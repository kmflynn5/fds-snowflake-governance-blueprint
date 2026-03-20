<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Intake Interview — Gap Specification

*Identified via dry-run session on 2026-03-20 against scripts/intake_interview.py*
*Dry-run scenario: 2 ingestion connectors (Fivetran, Airflow), 1 transformer (dbt Cloud), 2 BI tools (Looker, Sigma), 4 default personas, standard tag taxonomy, 1 FIREFIGHTER contact.*

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | 2 |
| High | 4 |
| Medium | 7 |
| Low | 4 |

---

## Critical — Blocks Client Use

### C1: Brownfield mode is a stub

**Location:** `cli()` and all `_section_*` functions
**Description:** `brownfield_context` is loaded from `intake/survey_output/*.json` and passed to every section function, but no section function reads from it. The brownfield interview runs identically to greenfield — no pre-population, no skip logic, no "we found X in your environment, confirm?" prompts.
**Expected behaviour:** When `--brownfield` is passed, sections should pre-populate from audit data where possible. For example:
- Section 2 (Ingestion): detect existing connectors from 1.8 service account patterns or 1.3 direct grants and offer to confirm rather than re-enter from scratch.
- Section 5 (Warehouses): pre-populate names and sizes from 1.4 warehouse inventory.
- Section 6 (Team): pre-populate personas from 1.3 human role assignments.
- Gap report findings should surface as context before each relevant section ("We found 2 users holding OBJ_ roles directly — you may want to define functional roles that cover their current access").

---

### C2: Only one transformation tool allowed

**Location:** `_section_transformation()`
**Description:** The function has a single `if not _confirm → return` gate with no while loop. A client with multiple transformation tools (e.g. dbt_prod + dbt_staging, or dbt + a custom Python pipeline) cannot add more than one.
**Expected behaviour:** Match the pattern used in `_section_ingestion()` and `_section_consumption()` — a `while True` loop with a per-iteration confirm to add another.

---

## High — Degrades Client Experience Significantly

### H1: decisions.md decisions table is hardcoded

**Location:** `_write_decisions_md()`
**Description:** The decisions table contains five rows with static text. Only the "Maturity target" row correctly reads from `context['maturity_target']`. The other four rows are baked in regardless of what the client chose. A client signing off on the decisions log expects it to reflect their actual answers, not generic FDS defaults.
**Expected behaviour:** Decisions should be dynamically generated from interview answers. At minimum: warehouse topology (single vs. workload-separated — derived from whether they kept the three defaults or customised), connector role count, number of custom personas, custom vs. default tag values chosen. The static rows can remain as context but should be tagged as "FDS standard" vs. "client decision".

---

### H2: No resume or edit path

**Location:** `cli()`
**Description:** If a client makes a mistake mid-interview, or changes their mind after completing a section, there is no way to go back. The only option is to abort and restart from Section 1. On a 45-minute client call this is a significant problem.
**Expected behaviour (two options — pick one):**
- **Option A (preferred):** Write a partial state file (e.g. `intake/.interview_state.json`) after each section completes. On restart, detect the state file and offer to resume from the last completed section.
- **Option B:** Add a `--edit` flag that loads existing `connectors.yaml` / `team.yaml` and allows re-running individual sections without touching others.

---

### H3: tags.yaml silently corrupts on accidental single-char input

**Location:** `_section_tags()`, environment values prompt
**Demonstrated in dry-run:** The environment values prompt received `n` (a single character) because the prior prompt consumed the intended Enter keystroke. The YAML was written with `values: [n]` — no error, no warning. This will silently produce broken Terraform variables.
**Expected behaviour:** Validate that tag value inputs parse to a non-empty list of reasonable strings. Reject inputs that are a single character, contain only punctuation, or produce fewer than 2 values for tags that have an explicit default of 3+ values. Re-prompt with a clear error message.

---

### H4: Section 6 privilege confirms are dense and mis-entry-prone

**Location:** `_section_team()`, DB access privilege block
**Demonstrated in dry-run:** In a piped session representing a real client answer sequence, ANALYTICS database access for DATA_ENGINEER received SELECT+INSERT but not CREATE TABLE+CREATE SCHEMA, even though the intended inputs were Y for all four. The four back-to-back `[y/N]` confirms with no summary are easy to mis-enter in both interactive and scripted contexts.
**Expected behaviour:** After collecting all privileges for a DB entry, show a confirmation line before moving on:
`-> RAW_FIVETRAN: SELECT, INSERT — correct? [Y/n]`
This gives the client one moment to catch errors without requiring a full restart.

---

## Medium — Polish Gaps

### M1: FIREFIGHTER emergency config not written to team.yaml

**Location:** `_section_emergency_access()` → `_write_team_yaml()`
**Description:** Emergency access config (authorized contacts, notification process, deactivation SLA) is written to decisions.md only. `generate_tf.py` may need this data to generate the FIREFIGHTER role grants or to populate a runbook. Verify what `generate_tf.py` expects; if it reads team.yaml for FIREFIGHTER config, this is a data gap.
**Expected behaviour:** Write emergency config to team.yaml under an `emergency_access:` key in addition to decisions.md.

---

### M2: No validation on warehouse names

**Location:** `_section_warehouses()`, custom warehouse name prompt
**Description:** The custom warehouse name prompt accepts any string — lowercase, spaces, special characters. Snowflake warehouse names must be uppercase identifiers. A client entering `my warehouse` or `wh-ingest-v2` will produce broken Terraform.
**Expected behaviour:** Normalise to uppercase and replace spaces/hyphens with underscores. Reject names that contain characters outside `[A-Z0-9_]` after normalisation.

---

### M3: Per-DB-entry reason prompt is friction-heavy

**Location:** `_section_team()`, `_section_ingestion()`
**Description:** Every database access entry requires a "reason" prompt. In a session with 4 personas × 2 databases = 8 reason prompts, plus connector reason prompts, the repetition fatigues clients and results in low-quality entries ("access needed", "for work", etc.).
**Expected behaviour:** Make the reason prompt optional (default: empty string). Add a role-level summary prompt instead, which is already present but currently collected in addition to the per-entry reasons.

---

### M4: No tags summary before write

**Location:** `cli()`, Preview section
**Description:** The preview before writing shows only connectors. Team personas and tag taxonomy are written without any client-facing summary. A client cannot verify their tag choices before they're committed to disk.
**Expected behaviour:** Extend the preview to show a one-line summary of team personas (names and warehouses) and a list of tag names with their value counts, before the "Write output files?" confirm.

---

### M5: Section 7 required tags are hardcoded

**Location:** `_section_tags()`
**Description:** `cost_center`, `environment`, and `owner` are always written as required tags regardless of client input. There is no way to add a custom required tag (e.g. `business_unit`, `data_product`, `regulatory_domain`) during the interview.
**Expected behaviour:** After the default required tags are confirmed, add a loop: "Add a custom required tag? [y/N]" — collecting name, values, and apply_to. Match the pattern used in the connectors and team sections.

---

### M6: decisions.md Change Log has empty Date and Author

**Location:** `_write_decisions_md()`
**Description:** The Change Log table is written with empty Date and Author for the initial intake row. These should be populated automatically.
**Expected behaviour:** Populate Date with today's date (`datetime.date.today().isoformat()`). Add an optional `_prompt("Your name (for the decision log)")` at the end of the interview, default empty.

---

### M7: WH_TRANSFORM default credit budget is likely too low

**Location:** `_section_warehouses()`, defaults list
**Description:** `WH_TRANSFORM` defaults to 200 credits/month. For a client running dbt Cloud on a SMALL warehouse, 200 credits is low — a 4-hour daily dbt run on SMALL consumes ~60 credits/day, which exceeds 200 in under 4 days. Clients who accept the default without thinking will hit the resource monitor hard limit.
**Expected behaviour:** Increase default to 500. Add a NOTE after the TRANSFORM budget prompt: "dbt on SMALL typically uses 50–150 credits/day depending on model count."

---

## Low — Nice to Have

### L1: The Claude Code tip references non-existent skills — **CLOSED**

**Location:** `cli()`, opening message
**Resolution:** Skills exist at `.claude/skills/intake-greenfield.md` and `.claude/skills/intake-review.md`. Tip is valid.

---

### L2: Brownfield mode shows no audit context before sections

**Location:** `cli()`, brownfield branch
**Description:** Even before brownfield pre-population is implemented (C1), the loaded audit data could at minimum be summarised at the top: "We found 4 warehouses, 3 users, 2 direct grants — here is your gap report summary." This orients the client before the interview starts.
**Expected behaviour:** Print the gap report summary (critical/standard finding counts and top findings) from the loaded audit data before Section 1.

---

### L3: No --dry-run / --preview flag for the interview itself

**Location:** `cli()`
**Description:** There is no way to run the interview and see the YAML output without writing files. Useful for validating inputs before overwriting existing intake configs.
**Expected behaviour:** Add `--dry-run` flag that prints generated YAML to stdout instead of writing files.

---

### L4: Connector name uppercasing is inconsistent — **CLOSED**

**Location:** `_section_ingestion()`, `_section_transformation()`, `_section_consumption()`
**Resolution:** All three sections now call `_normalize_identifier()` which uppercases and validates. The `CONN_` prefix is applied by `generate_tf.py` at codegen time — YAML stores bare names. Behavior is correct and consistent.

---

## Files to Modify

| File | Gaps addressed |
|------|---------------|
| `scripts/intake_interview.py` | All gaps above |
| `intake/team.yaml` schema | M1 (add emergency_access key) |
| `scripts/generate_tf.py` | M1 (consume emergency_access from team.yaml if needed) |
| `.claude/` skills | L1 (create /intake-greenfield skill) |

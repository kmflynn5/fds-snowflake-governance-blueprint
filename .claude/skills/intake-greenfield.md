# /intake-greenfield

Run a guided greenfield Snowflake governance intake session.

## What this does

This skill walks a new client through the governance intake questionnaire
(docs/greenfield_intake.md), explains trade-offs, recommends defaults,
and produces:

- `intake/connectors.yaml` — one entry per integration
- `intake/tags.yaml` — tag taxonomy
- `intake/team.yaml` — one entry per human functional persona
- `intake/decisions.md` — decision log with rationale

## Instructions

1. **Read context first.** Before starting, read:
   - `docs/PHILOSOPHY.md` — governance principles
   - `docs/greenfield_intake.md` — the full questionnaire
   - `intake/connectors.yaml` (if it exists) — current state

2. **Run the CLI to capture structured output:**
   ```bash
   uv run scripts/intake_interview.py --greenfield
   ```
   The CLI covers all sections including **Section 6 — Team Structure**, which generates
   `intake/team.yaml` with one entry per human functional persona.

3. **Add conversational layer.** As each section is completed:
   - Explain the trade-off behind each design choice
   - Reference the relevant section of PHILOSOPHY.md
   - Capture additional nuance or constraints in decisions.md

4. **Key questions to probe:**
   - Section 2 (Ingestion): For each tool — does the vendor manage the
     credential? Does it need read-back access? Is there a Snowpipe
     component that needs `CREATE PIPE`?
   - Section 3 (Transformation): Does dbt create schemas dynamically?
     How many environments (prod/dev)? Separate service accounts?
   - **Section 5 (Team Structure):** How many people access Snowflake
     directly (not through a BI tool)? What are their roles and functions?
     Do engineers need write access to the analytics layer? Should each
     persona type have its own dedicated warehouse, or share WH_ANALYTICS?
     Any external apps or scripts needing read-only access that should get
     a distinct functional role for audit trail purposes?
   - Section 6 (Warehouses): Is WH_ANALYTICS expected to be multi-cluster?
     What's the actual cost budget vs the default?
   - Section 9 (FIREFIGHTER): Who specifically is on the activation list?
     What's the Slack/PagerDuty alert channel?

5. **Review generated team.yaml.** After the CLI completes:
   - Read the generated file: `Read intake/team.yaml`
   - Walk through each persona with the user — confirm warehouse, database scope, privileges
   - Check the codegen output for **SCOPE-DOWN REMINDERS**: when the operator entered named
     schemas during intake, `schemas` is written as `["*"]` for greenfield safety and the
     intended schema list is stored in `scope_to`. Once those schemas exist, update `team.yaml`
     to replace `schemas: ["*"]` with the `scope_to` list and re-run codegen.
   - Run `uv run scripts/generate_tf.py --team intake/team.yaml` and confirm any reminders

6. **Review generated connectors.yaml.** After the CLI completes:
   - Read the generated file: `Read intake/connectors.yaml`
   - Walk through each connector with the user — confirm name, type,
     privileges, warehouse assignment
   - Check that no connector has broader privileges than necessary
   - Reference PHILOSOPHY.md §Least Privilege Standard for any discussion

7. **Update decisions.md** with any nuance not captured by the CLI answers.
   Common additions:
   - Why a specific database structure was chosen over alternatives
   - Any deferred decisions (e.g. "multi-cluster deferred until analyst
     count exceeds 5")
   - Brownfield migration constraints that apply even in a new environment
     (e.g. "migrating from existing Matillion setup — connectors must match
     existing credential names during transition")

## References

- docs/PHILOSOPHY.md — governance principles (read before every session)
- docs/greenfield_intake.md — full questionnaire with context
- docs/SPEC.md §1.2 — connectors.yaml schema
- docs/SPEC.md §1.3 — tags.yaml schema

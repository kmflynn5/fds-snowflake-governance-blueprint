# /intake-greenfield

Run a guided greenfield Snowflake governance intake session.

## What this does

This skill walks a new client through the governance intake questionnaire
(docs/greenfield_intake.md), explains trade-offs, recommends defaults,
and produces:

- `intake/connectors.yaml` — one entry per integration
- `intake/tags.yaml` — tag taxonomy
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
   - Section 5 (Warehouses): Is WH_ANALYTICS expected to be multi-cluster?
     What's the actual cost budget vs the default?
   - Section 8 (FIREFIGHTER): Who specifically is on the activation list?
     What's the Slack/PagerDuty alert channel?

5. **Review generated connectors.yaml.** After the CLI completes:
   - Read the generated file: `Read intake/connectors.yaml`
   - Walk through each connector with the user — confirm name, type,
     privileges, warehouse assignment
   - Check that no connector has broader privileges than necessary
   - Reference PHILOSOPHY.md §Least Privilege Standard for any discussion

6. **Update decisions.md** with any nuance not captured by the CLI answers.
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

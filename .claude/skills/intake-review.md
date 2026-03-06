# /intake-review

Review brownfield audit findings and run the brownfield intake interview.

## What this does

This skill takes the output of `scripts/audit.py` (survey JSON files + gap report)
and helps the human engineer review findings, understand implications, fill gaps,
and produce governance config files.

Outputs:
- `intake/connectors.yaml`
- `intake/tags.yaml`
- `intake/decisions.md`

## Prerequisites

The audit must have been run first:
```bash
uv run scripts/audit.py audit
uv run scripts/audit.py report
```

## Instructions

1. **Read audit context first:**
   ```bash
   Read intake/gap_report.md
   ```
   Then read each JSON file in `intake/survey_output/` that has findings.

2. **Work through critical findings first** (from gap_report.md):
   - For each critical finding, explain the implication to the user
   - Reference the relevant PHILOSOPHY.md section
   - Ask: "What's the story behind this? Is there a reason it's set up this way?"
   - Capture the answer in decisions.md

   Common critical findings:
   - **ACCOUNTADMIN active users:** "Who are these users? Are they using ACCOUNTADMIN
     for routine work or genuine emergencies? What privilege do they actually need?"
   - **Direct object grants to users:** "Who granted these? What do these users do?
     We'll need to migrate these to object roles."
   - **Unmonitored warehouses:** "Has there been any cost surprise from these? What's
     a reasonable monthly budget?"

3. **Work through standard findings:**
   - Ad-hoc role names: map each to an owner and purpose
   - Shared service accounts: identify what they do, whether splitting is feasible now
   - Missing tags: note as accepted gap for Walk stage

4. **Fill gaps in knowledge** (questions the audit can't answer):
   - For dormant service accounts (no activity 30+ days): "Is this intentional?
     Seasonal workload? Safe to deactivate?"
   - For high-ACCOUNTADMIN usage: "What was the operational need? Is there a
     recurring task running as ACCOUNTADMIN?"
   - For shared service accounts: "What integration does this actually serve?
     What would break if we created separate accounts?"

5. **Run the brownfield interview:**
   ```bash
   uv run scripts/intake_interview.py --brownfield
   ```

6. **Review generated connectors.yaml:**
   - Read: `Read intake/connectors.yaml`
   - For each connector: confirm this matches what the audit showed
   - Note any legacy connectors that can't be migrated immediately —
     document in decisions.md as accepted technical debt with a target date

7. **Update decisions.md** with:
   - Which critical findings are addressed immediately vs. deferred
   - Migration sequencing decisions (which connectors to migrate first)
   - Any constraints (change freezes, vendor dependencies, hardcoded role names)
   - Sign-off contacts and dates

## Key questions for brownfield sessions

From docs/brownfield_intake.md Part 2:

**Role history (§2.1):** For each ad-hoc role — what was it created for? Is it
still actively used? What would break if removed?

**Service account mapping (§2.2):** Map every service account to a single integration
and owner. Is there a timeline constraint on splitting shared accounts?

**Warehouse usage (§2.3):** Were current warehouses set up intentionally? Are there
workloads that should be isolated but currently share a warehouse?

**Migration appetite (§2.6):** What's the target maturity stage? Is there a deadline?
How much disruption is acceptable?

## References

- docs/PHILOSOPHY.md §Brownfield Compromise — acceptable vs. unacceptable compromises
- docs/brownfield_intake.md Part 2 — full targeted interview questions
- docs/brownfield_intake.md Part 3 — findings summary template
- docs/SPEC.md §Part 6 — migration runbook reference

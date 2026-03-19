# Brownfield Testing Plan — Simulated Client Audit

Validates the full audit pipeline (`audit.py keygen → audit → report`) against
injected governance violations, giving confidence the tooling catches real
brownfield problems before a live client engagement.

---

## Injections and Expected Findings

| Injection | Audit section | Severity |
|-----------|--------------|----------|
| ACCOUNTADMIN granted to `USER_BF_TEST` | 1.2 accountadmin_users | CRITICAL |
| Direct USAGE grant on RAW_FIVETRAN to `USER_BF_TEST` | 1.3 direct_grants | CRITICAL |
| `OBJ_RAW_FIVETRAN_WRITER` granted to `USER_BF_TEST` | 1.3 human_role_assignments | STANDARD |
| `LEGACY_LOADER` ad-hoc role created | 1.1 roles | STANDARD |
| FIREFIGHTER granted to `USER_BF_TEST` | 1.1 grants_to_roles | CRITICAL |
| `BREAK_GLASS_TEMP` role created + granted to `USER_BF_TEST` | 1.1 grants_to_roles | CRITICAL |
| `WH_BROWNFIELD_UNMONITORED` — no resource monitor | 1.5 unmonitored_warehouses | CRITICAL |
| Operational SELECT run as ACCOUNTADMIN | 1.7 accountadmin_queries | CRITICAL *(45–180 min latency)* |

---

## Runbook

### Part 1 — Inject

```bash
# Our greenfield setup uses the named 'admin' connection (has ACCOUNTADMIN).
# On a client account, substitute --connection admin with --role ACCOUNTADMIN
# against whichever connection profile is configured for that account.
snow sql -f scripts/brownfield_inject.sql --connection admin
```

Note the timestamp when this completes. Section 1.7 findings require 45–180
minutes for `query_history` to populate — plan your audit window accordingly.

### Part 2 — Audit setup

Generate a keypair and set up the auditor user if not already done:

```bash
uv run scripts/audit.py keygen
# Note: private key saved to audit_key.pem (gitignored)
```

Run the auditor setup SQL as SECURITYADMIN:

```bash
snow sql -f scripts/audit_setup.sql --connection admin --role SECURITYADMIN
```

Edit `audit_setup.sql` first to substitute `<WH_NAME>` → `WH_INGEST` and
`RSA_PUBLIC_KEY` with the public key printed by `keygen`.

Create `audit.env` (gitignored):

```bash
SNOWFLAKE_ACCOUNT="<org>-<account>"
SNOWFLAKE_USER="FDS_AUDITOR_USER"
SNOWFLAKE_PRIVATE_KEY_PATH="~/.snowflake/audit_key.pem"
SNOWFLAKE_WAREHOUSE="WH_INGEST"
```

### Part 3 — Run audit

```bash
set -a; source audit.env; set +a
uv run scripts/audit.py audit --output-dir intake/survey_output
uv run scripts/audit.py report
```

### Part 4 — Verify findings

Open `intake/gap_report.md` and confirm the following appear:

**Critical findings expected:**
- Human users with ACCOUNTADMIN assigned (`USER_BF_TEST`)
- Direct object grants to users detected
- Warehouses without resource monitors (`WH_BROWNFIELD_UNMONITORED`)
- Break-glass / dormant role(s) assigned to users (`FIREFIGHTER`, `BREAK_GLASS_TEMP`)
- ACCOUNTADMIN used for routine operational queries *(requires query_history window)*

**Standard findings expected:**
- Ad-hoc role names detected (`LEGACY_LOADER`)
- Humans assigned directly to object roles (`USER_BF_TEST` → `OBJ_RAW_FIVETRAN_WRITER`)

### Part 5 — Before/after FIREFIGHTER validation

This validates the incident-response flow:

1. Confirm both `FIREFIGHTER` and `BREAK_GLASS_TEMP` appear in the break-glass
   finding in `gap_report.md`.
2. Run `scripts/brownfield_teardown.sql`:
   ```bash
   snow sql -f scripts/brownfield_teardown.sql --connection admin
   ```
3. Re-run the audit:
   ```bash
   uv run scripts/audit.py audit --output-dir intake/survey_output
   uv run scripts/audit.py report
   ```
4. Verify the break-glass finding is **absent** from the second report — clean
   bill of health. This confirms the "before" and "after" audit flow works.

### Part 6 — Cleanup

After all verification is complete:

```bash
# If not already run in Part 5:
snow sql -f scripts/brownfield_teardown.sql --connection admin

# Remove auditor user and credentials:
snow sql -f scripts/audit_teardown.sql --connection admin --role SECURITYADMIN
```

---

## Verification Checklist

- [ ] `gap_report.md` Critical: ACCOUNTADMIN user assignment (`USER_BF_TEST`)
- [ ] `gap_report.md` Critical: Direct object grants to users
- [ ] `gap_report.md` Critical: Unmonitored warehouse (`WH_BROWNFIELD_UNMONITORED`)
- [ ] `gap_report.md` Critical: Break-glass roles (`FIREFIGHTER` + `BREAK_GLASS_TEMP` in one finding)
- [ ] `gap_report.md` Critical: ACCOUNTADMIN routine queries *(after query_history latency)*
- [ ] `gap_report.md` Standard: Ad-hoc roles (`LEGACY_LOADER`)
- [ ] `gap_report.md` Standard: Humans on OBJ_ roles (`USER_BF_TEST`)
- [ ] Second audit after teardown: no break-glass finding present
- [ ] `intake/survey_output/` — all 8 JSON section files present
- [ ] `scripts/audit_teardown.sql` removes FDS_AUDITOR_USER and FDS_AUDITOR_TEMP cleanly

---

## Notes

**Query history latency:** `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` has a
45–180 minute lag. If section 1.7 is empty on first audit run, wait and
re-run.

**Break-glass pattern matching:** `audit.py` uses `SENSITIVE_ROLE_PATTERNS`
(see top of file) to catch both our `FIREFIGHTER` role and common client
break-glass naming variants (`BREAK_GLASS`, `EMERGENCY_ADMIN`, `FIXIT`, etc.).
Both `FIREFIGHTER` and `BREAK_GLASS_TEMP` should appear in a single consolidated
finding, not two separate findings.

**Column names:** The `grants_to_roles` check in `report()` uses columns
`privilege_or_role`, `granted_to`, and `grantee_name` — these are aliased in
the `1_1_role_inventory` survey query and match the Snowflake schema exactly.

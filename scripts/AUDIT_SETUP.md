# Brownfield Audit Setup Guide

*Flynn Data Services — Pre-Audit Instructions*

This guide covers the one-time setup required before running the automated brownfield audit
(`scripts/audit.py`). The entire process takes approximately 5 minutes to set up and 2 minutes
to tear down.

---

## What the Audit Does

The audit script connects to your Snowflake environment using a temporary, read-only audit user
and runs survey queries covering:

- Role inventory and grant hierarchy
- User inventory and service account patterns
- Direct object grants to users (governance violation check)
- Warehouse inventory and usage
- Resource monitor coverage
- Tag coverage
- Recent ACCOUNTADMIN activity
- Service account activity patterns

Results are saved to `intake/survey_output/` as JSON files, and a gap report is generated at
`intake/gap_report.md`.

---

## What Access Is Granted

`FDS_AUDITOR_TEMP` receives exactly two grants:

1. **`IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE`** — read-only access to `account_usage` metadata
   views. This allows querying role hierarchies, grant history, warehouse stats, and query history
   metadata. It cannot read any user table data.
2. **`USAGE ON WAREHOUSE <WH_NAME>`** — permission to execute queries. Any XS warehouse works.

**`FDS_AUDITOR_TEMP` has zero access to any user database or table.** It can only read Snowflake
account metadata.

---

## Step-by-Step Instructions

### Step 1: Generate the Audit Keypair

Run this on the machine where you'll execute the audit:

```bash
uv run scripts/audit.py keygen
```

This generates `audit_key.p8` (private key, stay local) and prints the public key to stdout.

### Step 2: Share the Public Key with the Client

Send the client the public key output. They will paste it into `audit_setup.sql`.

### Step 3: Client Runs `audit_setup.sql`

The client runs the following as SECURITYADMIN (or ACCOUNTADMIN):

```sql
-- Replace placeholders before running:
--   <WH_NAME>   → smallest available warehouse (e.g. COMPUTE_WH)
--   <public key> → output from Step 1
```

See `scripts/audit_setup.sql` for the full script.

### Step 4: Configure Environment Variables

```bash
export SNOWFLAKE_ACCOUNT="xy12345.us-east-1"
export SNOWFLAKE_USER="FDS_AUDITOR_USER"
export SNOWFLAKE_PRIVATE_KEY_PATH="./audit_key.p8"
export SNOWFLAKE_WAREHOUSE="<WH_NAME>"
```

### Step 5: Run the Audit

```bash
# Dry run first (prints queries, no execution)
uv run scripts/audit.py audit --dry-run

# Full audit
uv run scripts/audit.py audit

# Generate gap report from saved results
uv run scripts/audit.py report
```

### Step 6: Client Runs `audit_teardown.sql`

After the audit is complete and results are saved, the client runs:

```sql
DROP USER IF EXISTS FDS_AUDITOR_USER;
DROP ROLE IF EXISTS FDS_AUDITOR_TEMP;
```

See `scripts/audit_teardown.sql`.

---

## FAQ

**Q: What if we can't grant IMPORTED PRIVILEGES on SNOWFLAKE?**

Some organizations restrict access to the SNOWFLAKE system database. If IMPORTED PRIVILEGES
cannot be granted, the audit can use INFORMATION_SCHEMA as a fallback. INFORMATION_SCHEMA
provides less comprehensive data (no historical query history, no deleted object tracking), but
covers the most critical checks (current role grants, user inventory, warehouse inventory).

Run with the fallback flag: `uv run scripts/audit.py audit --use-information-schema`

Note that the gap report will indicate which findings could not be verified due to limited access.

**Q: Does the audit generate any charges?**

The audit runs lightweight metadata queries against account_usage views and a small number of
INFORMATION_SCHEMA queries. These run on an XS warehouse. Typical audit cost: well under 1 credit.

**Q: Can we run this against a non-production environment?**

Yes. The audit reads environment-level metadata, not database-specific data. Running against
a production environment gives the most accurate picture of production grants and usage patterns.

**Q: How long does the audit take to run?**

Approximately 2–5 minutes depending on environment size. The query against query_history
(30–90 day lookback) is the slowest step.

**Q: Is the private key stored anywhere?**

The private key (`audit_key.p8`) is generated locally and never leaves your machine. It is
listed in `.gitignore`. Delete it after the audit is complete.

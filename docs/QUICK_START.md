<!--
Copyright 2026 Flynn Data Services. Licensed under the Apache License, Version 2.0.
See LICENSE at the root of this repository.
-->

# Quick Start

*Flynn Data Services — Step-by-step setup guide*

This document covers the full operational steps for both greenfield and brownfield
engagements. For the governance philosophy, see `docs/PHILOSOPHY.md`. For a
comprehensive trial run guide including Snowflake account setup and keypair generation,
see `docs/GREENFIELD_TESTING_PLAN.md`.

---

## Greenfield Engagement

```bash
# Install uv (if not already installed — see https://docs.astral.sh/uv/getting-started/installation/)
uv sync --group dev

# Set auth env vars in terraform/.env then source it (see docs/GREENFIELD_TESTING_PLAN.md §Step 2)
# SNOWFLAKE_ORGANIZATION_NAME, SNOWFLAKE_ACCOUNT_NAME, SNOWFLAKE_USER,
# SNOWFLAKE_PRIVATE_KEY_PATH, SNOWFLAKE_ROLE, SNOWFLAKE_AUTHENTICATOR=SNOWFLAKE_JWT
set -a; source terraform/.env; set +a

# Run the intake interview
uv run scripts/intake_interview.py --greenfield
# Tip: if you're working in Claude Code, /intake-greenfield runs a guided session

# Generate Terraform variables
uv run scripts/generate_tf.py

# Review output
python -m json.tool terraform/rbac.auto.tfvars.json

# Apply
cd terraform
terraform init -backend=false
terraform plan
terraform apply
```

---

## Brownfield Engagement

```bash
# Step 1: generate audit keypair
uv run scripts/audit.py keygen
# Share public key with client → client follows scripts/AUDIT_SETUP.md to create the audit user

# Step 2: run audit
export SNOWFLAKE_ORGANIZATION_NAME="<org-name>"
export SNOWFLAKE_ACCOUNT_NAME="<account-name>"
export SNOWFLAKE_USER="FDS_AUDITOR_USER"
export SNOWFLAKE_PRIVATE_KEY_PATH="./audit_key.p8"
export SNOWFLAKE_AUTHENTICATOR="SNOWFLAKE_JWT"
export SNOWFLAKE_WAREHOUSE="COMPUTE_WH"

uv run scripts/audit.py audit
uv run scripts/audit.py report

# Step 3: review findings + run intake
uv run scripts/intake_interview.py --brownfield
# Tip: if you're working in Claude Code, /intake-review runs a guided session

# Step 4: client runs scripts/audit_teardown.sql

# Step 5: generate + apply Terraform (same as greenfield)
uv run scripts/generate_tf.py
cd terraform && terraform init && terraform plan && terraform apply
```

---

## Running Tests

```bash
uv run pytest tests/unit/

# Brownfield audit dry run (no Snowflake required)
uv run scripts/audit.py audit --dry-run

# Codegen dry run
uv run scripts/generate_tf.py --dry-run
```

---

## Verifying Terraform

```bash
cd terraform
terraform init -backend=false
terraform validate
terraform fmt -check
```

---

*Flynn Data Services · flynndata.com · Last reviewed: March 2026*

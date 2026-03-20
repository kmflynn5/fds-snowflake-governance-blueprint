"""
scripts/audit.py — Brownfield environment audit tool

Connects to a live Snowflake environment (via FDS_AUDITOR_USER / FDS_AUDITOR_TEMP)
and runs the survey queries from docs/brownfield_intake.md Part 1 (1.1–1.8).

Usage:
    uv run scripts/audit.py keygen
    uv run scripts/audit.py audit [--dry-run] [--output-dir intake/survey_output]
    uv run scripts/audit.py report [survey-dir]

See scripts/AUDIT_SETUP.md for full setup instructions.
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# Sensitive role patterns — any user assignment to these roles is a critical
# finding. Covers our FIREFIGHTER role and common client break-glass names.
# ---------------------------------------------------------------------------

SENSITIVE_ROLE_PATTERNS = (
    "FIREFIGHTER",
    "BREAK_GLASS",
    "BREAKGLASS",
    "EMERGENCY",
    "FIXIT",
    "FIX_IT",
    "SYSADMIN_TEMP",
    "TEMP_ADMIN",
    "OVERRIDE",
    "INCIDENT",
    "HOTFIX",
    "HOT_FIX",
)

# ---------------------------------------------------------------------------
# Survey queries — mirrors brownfield_intake.md Part 1, sections 1.1–1.8
# ---------------------------------------------------------------------------

SURVEYS = {
    "1_1_role_inventory": {
        "description": "Role inventory — all account-level roles and grant hierarchy",
        "queries": {
            "roles": "SHOW ROLES",
            "grants_to_roles": textwrap.dedent("""
                SELECT
                  grantee_name,
                  granted_on,
                  name AS privilege_or_role,
                  privilege,
                  granted_to,
                  grant_option,
                  granted_by
                FROM snowflake.account_usage.grants_to_roles
                WHERE deleted_on IS NULL
                ORDER BY grantee_name, granted_on, name
            """).strip(),
            "user_role_grants": textwrap.dedent("""
                SELECT grantee_name AS user_name, role AS granted_role, granted_by
                FROM snowflake.account_usage.grants_to_users
                WHERE deleted_on IS NULL
                ORDER BY grantee_name, role
            """).strip(),
        },
    },
    "1_2_user_inventory": {
        "description": "User inventory — all users, roles, and service account patterns",
        "queries": {
            "users": textwrap.dedent("""
                SELECT name, login_name, email, default_role, last_success_login
                FROM snowflake.account_usage.users
                WHERE deleted_on IS NULL
                ORDER BY last_success_login DESC NULLS LAST
            """).strip(),
            "accountadmin_users": textwrap.dedent("""
                SELECT grantee_name AS user_name
                FROM snowflake.account_usage.grants_to_users
                WHERE role = 'ACCOUNTADMIN'
                  AND deleted_on IS NULL
            """).strip(),
        },
    },
    "1_3_direct_grants": {
        "description": "Direct object grants to users — should be zero in a governed environment",
        "queries": {
            "direct_grants": textwrap.dedent("""
                SELECT g.grantee_name AS user_name, g.role AS granted_role, g.granted_by, g.created_on
                FROM snowflake.account_usage.grants_to_users g
                JOIN snowflake.account_usage.users u
                  ON u.name = g.grantee_name AND u.deleted_on IS NULL
                WHERE g.deleted_on IS NULL
                  AND u.type NOT IN ('SERVICE', 'LEGACY_SERVICE')
                  AND g.role NOT IN (
                    'ACCOUNTADMIN', 'SYSADMIN', 'SECURITYADMIN', 'USERADMIN',
                    'PUBLIC', 'ORGADMIN'
                  )
                ORDER BY g.grantee_name, g.role
            """).strip(),
        },
    },
    "1_3_human_role_assignments": {
        "description": "Human user role assignments — which roles do non-service users hold",
        "queries": {
            "human_role_assignments": textwrap.dedent("""
                SELECT u.name AS user_name, u.login_name, u.type AS user_type,
                       g.role AS granted_role, u.last_success_login
                FROM snowflake.account_usage.users u
                LEFT JOIN snowflake.account_usage.grants_to_users g
                    ON u.name = g.grantee_name AND g.deleted_on IS NULL
                WHERE u.deleted_on IS NULL
                  AND u.type NOT IN ('SERVICE', 'LEGACY_SERVICE')
                ORDER BY u.last_success_login DESC NULLS LAST
            """).strip(),
        },
    },
    "1_4_warehouse_inventory": {
        "description": "Warehouse inventory — all warehouses and 30-day usage",
        "queries": {
            "warehouses": "SHOW WAREHOUSES",
            "warehouse_usage_30d": textwrap.dedent("""
                SELECT
                  warehouse_name,
                  SUM(credits_used) AS total_credits
                FROM snowflake.account_usage.warehouse_metering_history
                WHERE start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP)
                GROUP BY warehouse_name
                ORDER BY total_credits DESC
            """).strip(),
        },
    },
    "1_5_resource_monitor_coverage": {
        "description": "Resource monitor coverage — warehouses without monitors",
        "queries": {
            "warehouses": "SHOW WAREHOUSES",
            "resource_monitors": "SHOW RESOURCE MONITORS",
        },
    },
    "1_6_tag_coverage": {
        "description": "Tag coverage — tagged objects and untagged databases/schemas",
        "queries": {
            "tag_references": textwrap.dedent("""
                SELECT *
                FROM snowflake.account_usage.tag_references
                WHERE object_deleted IS NULL
                ORDER BY object_database, object_schema, object_name
            """).strip(),
            "databases_schemas": textwrap.dedent("""
                SELECT
                  table_catalog AS database_name,
                  table_schema AS schema_name,
                  COUNT(*) AS table_count
                FROM snowflake.account_usage.tables
                WHERE deleted IS NULL
                  AND table_schema NOT IN ('INFORMATION_SCHEMA')
                GROUP BY 1, 2
                ORDER BY 1, 2
            """).strip(),
        },
    },
    "1_7_accountadmin_activity": {
        "description": "Recent ACCOUNTADMIN activity — last 90 days",
        "queries": {
            "accountadmin_queries": textwrap.dedent("""
                SELECT
                  user_name,
                  role_name,
                  warehouse_name,
                  query_type,
                  query_text,
                  start_time
                FROM snowflake.account_usage.query_history
                WHERE role_name = 'ACCOUNTADMIN'
                  AND start_time >= DATEADD('day', -90, CURRENT_TIMESTAMP)
                ORDER BY start_time DESC
                LIMIT 100
            """).strip(),
        },
    },
    "1_8_service_account_patterns": {
        "description": "Service account activity patterns — query volume by user last 30 days",
        "queries": {
            "user_query_volume": textwrap.dedent("""
                SELECT
                  user_name,
                  role_name,
                  COUNT(*) AS query_count,
                  SUM(credits_used_cloud_services) AS cloud_service_credits,
                  MIN(start_time) AS first_seen,
                  MAX(start_time) AS last_seen
                FROM snowflake.account_usage.query_history
                WHERE start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP)
                GROUP BY user_name, role_name
                ORDER BY query_count DESC
            """).strip(),
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_connection():
    """Build a Snowflake connection from environment variables."""
    import snowflake.connector

    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    private_key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "")

    if not all([account, user, private_key_path]):
        raise click.ClickException(
            "Missing required environment variables. Set:\n"
            "  SNOWFLAKE_ACCOUNT\n"
            "  SNOWFLAKE_USER\n"
            "  SNOWFLAKE_PRIVATE_KEY_PATH\n"
            "  SNOWFLAKE_WAREHOUSE (optional)"
        )

    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    with open(private_key_path, "rb") as f:
        private_key = load_pem_private_key(f.read(), password=None)

    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat
    pkb = private_key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )

    conn = snowflake.connector.connect(
        account=account,
        user=user,
        private_key=pkb,
        warehouse=warehouse or None,
        role="FDS_AUDITOR_TEMP",
    )
    return conn


def _run_query(cursor, sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts."""
    cursor.execute(sql)
    columns = [col[0].lower() for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _serialize(obj):
    """JSON serializer for non-serializable types (datetime, Decimal, etc.)."""
    import datetime
    import decimal
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """FDS Snowflake governance audit tools."""


@cli.command()
def keygen():
    """Generate RSA keypair for the audit user.

    Outputs the public key to stdout for pasting into audit_setup.sql.
    Saves the private key to audit_key.pem in the ~/.snowflake directory.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Save private key to ~/.snowflake/ alongside snow CLI config so the path
    # is stable regardless of working directory.
    snowflake_dir = Path.home() / ".snowflake"
    snowflake_dir.mkdir(exist_ok=True)
    priv_path = snowflake_dir / "audit_key.pem"
    priv_path.write_bytes(
        private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    click.echo(f"Private key saved to: {priv_path}", err=True)
    click.echo("(Never commit this file — it's in .gitignore)", err=True)
    click.echo("", err=True)

    # Print public key for audit_setup.sql
    pub_pem = private_key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    # Snowflake expects the key body without PEM headers
    pub_lines = pub_pem.decode().strip().splitlines()
    pub_body = "".join(pub_lines[1:-1])  # strip -----BEGIN/END----- lines

    click.echo("Paste this into audit_setup.sql as RSA_PUBLIC_KEY:")
    click.echo(pub_body)


@cli.command()
@click.option("--dry-run", is_flag=True, help="Print queries without executing")
@click.option(
    "--output-dir",
    default="intake/survey_output",
    show_default=True,
    help="Directory for JSON output files",
)
@click.option(
    "--use-information-schema",
    is_flag=True,
    help="Fallback: use INFORMATION_SCHEMA instead of account_usage (less comprehensive)",
)
def audit(dry_run: bool, output_dir: str, use_information_schema: bool):
    """Run brownfield environment audit.

    Connects to Snowflake and runs survey queries from docs/brownfield_intake.md.
    Saves results to --output-dir as JSON files (one per section).

    Configure via environment variables:
        SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PRIVATE_KEY_PATH, SNOWFLAKE_WAREHOUSE
    """
    out_dir = Path(output_dir)

    if dry_run:
        click.echo("DRY RUN — queries will be printed but not executed\n")
        for section, config in SURVEYS.items():
            click.echo(f"## {section}: {config['description']}")
            for name, sql in config["queries"].items():
                click.echo(f"\n-- {name}\n{sql}\n")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Output directory: {out_dir.resolve()}")

    conn = _get_connection()
    cursor = conn.cursor()

    try:
        for section, config in SURVEYS.items():
            click.echo(f"\nRunning {section}: {config['description']} ...")
            section_results = {}

            for name, sql in config["queries"].items():
                click.echo(f"  [{name}] ", nl=False)
                try:
                    rows = _run_query(cursor, sql)
                    section_results[name] = rows
                    click.echo(f"{len(rows)} rows")
                except Exception as e:
                    click.echo(f"ERROR: {e}", err=True)
                    section_results[name] = {"error": str(e)}

            out_file = out_dir / f"{section}.json"
            out_file.write_text(
                json.dumps(section_results, indent=2, default=_serialize)
            )
            click.echo(f"  -> {out_file}")

    finally:
        cursor.close()
        conn.close()

    click.echo("\nAudit complete. Run 'uv run scripts/audit.py report' to generate gap report.")


@cli.command()
@click.argument("survey-dir", default="intake/survey_output")
def report(survey_dir: str):
    """Generate gap report from saved audit results.

    Reads JSON files from SURVEY_DIR and writes intake/gap_report.md.
    """
    survey_path = Path(survey_dir)
    if not survey_path.exists():
        raise click.ClickException(f"Survey directory not found: {survey_path}\nRun 'audit' first.")

    # Load all available sections
    data: dict[str, dict] = {}
    for json_file in sorted(survey_path.glob("*.json")):
        try:
            data[json_file.stem] = json.loads(json_file.read_text())
        except Exception as e:
            click.echo(f"Warning: could not read {json_file}: {e}", err=True)

    if not data:
        raise click.ClickException(f"No survey JSON files found in {survey_path}")

    # --- Derive findings ---
    critical = []
    standard = []
    stats: dict[str, int] = {}

    # 1.1 Role inventory
    roles = data.get("1_1_role_inventory", {}).get("roles", [])
    stats["role_count"] = len(roles)
    if isinstance(roles, list):
        # Flag roles without recognisable naming conventions
        ad_hoc_roles = [
            r.get("name", "") for r in roles
            if not any(
                r.get("name", "").startswith(p)
                for p in (
                    "CONN_", "OBJ_", "WH_", "TF_", "FDS_",
                    "ACCOUNTADMIN", "SYSADMIN", "SECURITYADMIN", "USERADMIN", "ORGADMIN",
                    "PUBLIC", "FIREFIGHTER", "BREAK_GLASS",
                    "AUDITOR", "LOADER", "TRANSFORMER", "ANALYST",
                )
            )
        ]
        if ad_hoc_roles:
            standard.append({
                "finding": "Ad-hoc role names detected",
                "evidence": f"{len(ad_hoc_roles)} roles without standard naming: {', '.join(ad_hoc_roles[:10])}",
                "priority": "medium",
                "remediation": "Map each role to a connector or functional role pattern and migrate",
            })

    # 1.1 Break-glass / dormant role assignments (FIREFIGHTER and client variants)
    # Primary source: grants_to_roles (has USER rows for role-to-user grants, ~2h latency).
    # Fallback source: user_role_grants from grants_to_users (lower latency).
    grants_to_roles = data.get("1_1_role_inventory", {}).get("grants_to_roles", [])
    user_role_grants = data.get("1_1_role_inventory", {}).get("user_role_grants", [])

    sensitive_assignments: list[dict] = []
    if isinstance(grants_to_roles, list):
        sensitive_assignments += [
            {"role": r.get("privilege_or_role", ""), "user": r.get("grantee_name", "")}
            for r in grants_to_roles
            if r.get("granted_to") == "USER"
            and any(pat in r.get("privilege_or_role", "").upper() for pat in SENSITIVE_ROLE_PATTERNS)
        ]
    if isinstance(user_role_grants, list):
        seen = {(s["role"], s["user"]) for s in sensitive_assignments}
        sensitive_assignments += [
            {"role": r.get("granted_role", ""), "user": r.get("user_name", "")}
            for r in user_role_grants
            if any(pat in r.get("granted_role", "").upper() for pat in SENSITIVE_ROLE_PATTERNS)
            and (r.get("granted_role", ""), r.get("user_name", "")) not in seen
        ]

    if sensitive_assignments:
        by_role: dict[str, list[str]] = {}
        for s in sensitive_assignments:
            by_role.setdefault(s["role"], []).append(s["user"])
        evidence_parts = [f"{role}→{', '.join(users)}" for role, users in by_role.items()]
        critical.append({
            "finding": "Break-glass / dormant role(s) assigned to users",
            "evidence": "; ".join(evidence_parts),
            "risk": "Emergency roles must have zero user assignments outside active incidents (PHILOSOPHY.md §4)",
            "remediation": "Revoke all assignments immediately. Document any active incident. Add daily assertion to eval suite.",
        })

    # 1.1 SYSADMIN granted directly to users (should only be held via TF_SYSADMIN)
    sysadmin_from_gtr = [
        r.get("grantee_name", "") for r in (grants_to_roles if isinstance(grants_to_roles, list) else [])
        if r.get("privilege_or_role") == "SYSADMIN" and r.get("granted_to") == "USER"
    ]
    sysadmin_from_urg = [
        r.get("user_name", "") for r in (user_role_grants if isinstance(user_role_grants, list) else [])
        if r.get("granted_role") == "SYSADMIN"
    ]
    sysadmin_users = list(dict.fromkeys(sysadmin_from_gtr + sysadmin_from_urg))  # dedup, preserve order
    if sysadmin_users:
        critical.append({
            "finding": "SYSADMIN granted directly to users",
            "evidence": f"{len(sysadmin_users)} user(s): {', '.join(sysadmin_users)}",
            "risk": "SYSADMIN should only be granted to service roles (TF_SYSADMIN), not humans (PHILOSOPHY.md §4)",
            "remediation": "Remove SYSADMIN from all human users; use scoped functional roles instead",
        })

    # 1.2 User inventory — ACCOUNTADMIN users (cross-referenced with 1.7 activity)
    acct_admin_users = data.get("1_2_user_inventory", {}).get("accountadmin_users", [])
    if isinstance(acct_admin_users, list) and acct_admin_users:
        aa_names = {r.get("user_name", "") for r in acct_admin_users}

        # Cross-reference with 1.7 operational query activity
        aa_queries = data.get("1_7_accountadmin_activity", {}).get("accountadmin_queries", [])
        operational_aa_users = {
            q.get("user_name", "") for q in (aa_queries if isinstance(aa_queries, list) else [])
            if q.get("query_type", "") in ("SELECT", "INSERT", "UPDATE")
        }

        active = sorted(aa_names & operational_aa_users)   # assigned + actively used
        dormant = sorted(aa_names - operational_aa_users)  # assigned but no routine use

        if active:
            critical.append({
                "finding": "ACCOUNTADMIN assigned to users AND used for routine queries",
                "evidence": f"{len(active)} user(s) actively running SELECT/INSERT/UPDATE as ACCOUNTADMIN: {', '.join(active)}",
                "risk": "ACCOUNTADMIN is being used as a daily-driver role, not reserved for emergencies (PHILOSOPHY.md §4)",
                "remediation": "Identify required privileges; create scoped roles; revoke ACCOUNTADMIN",
            })
        if dormant:
            standard.append({
                "finding": "ACCOUNTADMIN assigned but not used for routine queries",
                "evidence": f"{len(dormant)} user(s) hold ACCOUNTADMIN with no operational query activity: {', '.join(dormant)}",
                "priority": "medium",
                "remediation": "Revoke ACCOUNTADMIN; grant FIREFIGHTER for break-glass access instead (PHILOSOPHY.md §4)",
            })

    users = data.get("1_2_user_inventory", {}).get("users", [])
    stats["user_count"] = len(users) if isinstance(users, list) else 0

    # 1.3 Direct grants to users
    direct_grants = data.get("1_3_direct_grants", {}).get("direct_grants", [])
    if isinstance(direct_grants, list) and direct_grants:
        critical.append({
            "finding": "Direct object grants to users detected",
            "evidence": f"{len(direct_grants)} direct grant(s) — see 1_3_direct_grants.json for details",
            "risk": "Direct grants bypass the role hierarchy entirely (PHILOSOPHY.md §2)",
            "remediation": "Migrate all direct grants to object roles; revoke direct grants",
        })

    # 1.3 Human role assignments — flag humans holding object roles directly
    human_assignments = data.get("1_3_human_role_assignments", {}).get("human_role_assignments", [])
    if isinstance(human_assignments, list):
        obj_role_holders = [
            r for r in human_assignments
            if isinstance(r.get("granted_role"), str) and r["granted_role"].startswith("OBJ_")
        ]
        if obj_role_holders:
            users_with_obj = sorted({r.get("user_name", "") for r in obj_role_holders})
            standard.append({
                "finding": "Humans assigned directly to object roles — should hold only functional roles",
                "evidence": f"{len(obj_role_holders)} assignment(s) across {len(users_with_obj)} user(s): {', '.join(users_with_obj[:5])}",
                "priority": "medium",
                "remediation": "Assign humans to functional roles only; object roles should be held by connector/functional roles",
            })

    # 1.4 Warehouse inventory
    warehouses = data.get("1_4_warehouse_inventory", {}).get("warehouses", [])
    stats["warehouse_count"] = len(warehouses) if isinstance(warehouses, list) else 0

    # 1.5 Resource monitor coverage
    # SHOW WAREHOUSES returns a 'resource_monitor' column; null/empty means unmonitored.
    wh_list = data.get("1_5_resource_monitor_coverage", {}).get("warehouses", [])
    if not wh_list:
        # fall back to 1_4 warehouse data if 1_5 is unavailable
        wh_list = warehouses
    unmonitored_names = [
        w.get("name", "") for w in (wh_list if isinstance(wh_list, list) else [])
        if not w.get("resource_monitor") or w.get("resource_monitor") in ("null", "", None)
    ]
    stats["unmonitored_warehouse_count"] = len(unmonitored_names)
    if unmonitored_names:
        critical.append({
            "finding": "Warehouses without resource monitors",
            "evidence": f"{len(unmonitored_names)} unmonitored warehouse(s): {', '.join(unmonitored_names)}",
            "risk": "Uncontrolled cost exposure — no spend ceiling",
            "remediation": "Attach a resource monitor to every warehouse (SPEC.md §3 — Resource Monitor Defaults)",
        })

    # 1.6 Tag coverage
    tag_refs = data.get("1_6_tag_coverage", {}).get("tag_references", [])
    stats["tagged_object_count"] = len(tag_refs) if isinstance(tag_refs, list) else 0
    if stats["tagged_object_count"] == 0:
        standard.append({
            "finding": "No tag coverage detected",
            "evidence": "Zero tagged objects found in account_usage.tag_references",
            "priority": "low",
            "remediation": "Define tag taxonomy in tags.yaml and apply at Walk stage",
        })

    # 1.7 ACCOUNTADMIN activity
    aa_queries = data.get("1_7_accountadmin_activity", {}).get("accountadmin_queries", [])
    if isinstance(aa_queries, list) and aa_queries:
        # Check for non-DDL operational queries (SELECT, INSERT = routine use)
        operational = [q for q in aa_queries if q.get("query_type", "") in ("SELECT", "INSERT", "UPDATE")]
        if operational:
            critical.append({
                "finding": "ACCOUNTADMIN used for routine operational queries",
                "evidence": f"{len(operational)} SELECT/INSERT/UPDATE queries in last 90 days",
                "risk": "ACCOUNTADMIN is being used as a workaround, not for emergency intervention only (PHILOSOPHY.md §4)",
                "remediation": "Identify the actual privilege needed; create a scoped role; remove ACCOUNTADMIN usage",
            })

    # 1.8 Service account patterns
    user_volumes = data.get("1_8_service_account_patterns", {}).get("user_query_volume", [])
    if isinstance(user_volumes, list):
        shared_sa = [
            u for u in user_volumes
            if len([v for v in user_volumes if v.get("user_name") == u.get("user_name")]) > 1
        ]
        if shared_sa:
            standard.append({
                "finding": "Service accounts using multiple roles detected",
                "evidence": f"Multiple role usage by: {', '.join(set(u.get('user_name', '') for u in shared_sa[:5]))}",
                "priority": "medium",
                "remediation": "Each service account should use exactly one connector role (PHILOSOPHY.md §1)",
            })

    # --- Write report ---
    report_path = Path("intake/gap_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Brownfield Governance Gap Report",
        "*Generated by scripts/audit.py — Flynn Data Services*",
        "",
        "---",
        "",
        "## Summary Statistics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Roles | {stats.get('role_count', 'N/A')} |",
        f"| Users | {stats.get('user_count', 'N/A')} |",
        f"| Warehouses | {stats.get('warehouse_count', 'N/A')} |",
        f"| Unmonitored warehouses | {stats.get('unmonitored_warehouse_count', 'N/A')} |",
        f"| Tagged objects | {stats.get('tagged_object_count', 'N/A')} |",
        "",
        "---",
        "",
        "## Critical Findings",
        "*(Must be addressed before any other work proceeds)*",
        "",
    ]

    if critical:
        lines += ["| Finding | Evidence | Risk | Remediation |", "|---------|----------|------|-------------|"]
        for f in critical:
            lines.append(f"| {f['finding']} | {f['evidence']} | {f['risk']} | {f['remediation']} |")
    else:
        lines.append("*No critical findings. Proceed to standard findings.*")

    lines += [
        "",
        "---",
        "",
        "## Standard Findings",
        "*(Should be addressed as part of the migration)*",
        "",
    ]

    if standard:
        lines += ["| Finding | Evidence | Priority | Remediation |", "|---------|----------|----------|-------------|"]
        for f in standard:
            lines.append(f"| {f['finding']} | {f['evidence']} | {f.get('priority', 'medium')} | {f['remediation']} |")
    else:
        lines.append("*No standard findings.*")

    lines += [
        "",
        "---",
        "",
        "## Next Steps",
        "",
        "1. Review findings above with the client (see docs/brownfield_intake.md Part 2)",
        "2. Run the intake interview: `uv run scripts/intake_interview.py --brownfield`",
        "3. Review and finalize `intake/connectors.yaml` and `intake/decisions.md`",
        "4. Run codegen: `uv run scripts/generate_tf.py`",
        "5. Review `terraform/*.auto.tfvars.json` and apply",
    ]

    report_path.write_text("\n".join(lines) + "\n")
    click.echo(f"\nGap report written to: {report_path.resolve()}")

    # Summary to stdout
    click.echo(f"\n{'='*50}")
    click.echo(f"Critical findings: {len(critical)}")
    click.echo(f"Standard findings: {len(standard)}")


if __name__ == "__main__":
    cli()

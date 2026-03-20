"""
scripts/intake_interview.py — Interactive intake interview CLI

Walks through the intake questionnaire and generates config files.

Greenfield mode: asks all questions from docs/greenfield_intake.md
Brownfield mode: pre-populates from intake/survey_output/ + intake/gap_report.md,
                 asks only for gaps and decisions

Usage:
    uv run scripts/intake_interview.py --greenfield
    uv run scripts/intake_interview.py --brownfield
    uv run scripts/intake_interview.py --greenfield --output-dir custom/
    uv run scripts/intake_interview.py --greenfield --dry-run

Outputs:
    intake/connectors.yaml
    intake/tags.yaml
    intake/team.yaml
    intake/decisions.md
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

import click
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prompt(text: str, **kwargs) -> Any:
    """Wrapped click.prompt with consistent formatting."""
    click.echo("")
    return click.prompt(click.style(text, bold=True), **kwargs)


def _confirm(text: str, default: bool = True) -> bool:
    click.echo("")
    return click.confirm(click.style(text, bold=True), default=default)


def _section_header(title: str):
    click.echo("")
    click.echo(click.style("=" * 60, fg="blue"))
    click.echo(click.style(f"  {title}", fg="blue", bold=True))
    click.echo(click.style("=" * 60, fg="blue"))


def _note(text: str):
    click.echo(click.style(f"  NOTE: {text}", fg="yellow"))


def _normalize_identifier(label: str, raw: str) -> str:
    """Normalize to a Snowflake-safe uppercase identifier. Re-prompts until valid."""
    name = raw.strip().upper().replace(" ", "_").replace("-", "_")
    while not re.match(r'^[A-Z][A-Z0-9_]*$', name):
        click.echo(click.style(
            f"  '{name}' is not a valid Snowflake identifier. Use letters, digits, underscores only.",
            fg="red",
        ))
        raw = _prompt(label)
        name = raw.strip().upper().replace(" ", "_").replace("-", "_")
    return name


def _validate_tag_values(prompt_label: str, raw: str, min_count: int = 2) -> list[str]:
    """Validate tag values, re-prompting until valid. Returns a clean list."""
    while True:
        values = [v.strip().lower() for v in raw.split(",") if v.strip()]
        errors: list[str] = []
        for v in values:
            if len(v) == 1:
                errors.append(f"  '{v}' is a single character — check your input")
        if len(values) < min_count:
            errors.append(f"  at least {min_count} values required, got {len(values)}")
        if not errors:
            return values
        for e in errors:
            click.echo(click.style(e, fg="red"))
        raw = _prompt(prompt_label)


# ---------------------------------------------------------------------------
# State file helpers
# ---------------------------------------------------------------------------

def _save_state(state: dict, output_dir: Path):
    state_path = output_dir / ".interview_state.json"
    state_path.write_text(json.dumps(state, indent=2, default=str))


def _load_state(output_dir: Path) -> dict | None:
    state_path = output_dir / ".interview_state.json"
    if not state_path.exists():
        return None
    try:
        return json.loads(state_path.read_text())
    except Exception:
        return None


def _delete_state(output_dir: Path):
    state_path = output_dir / ".interview_state.json"
    if state_path.exists():
        state_path.unlink()


# ---------------------------------------------------------------------------
# Brownfield connector pattern detection
# ---------------------------------------------------------------------------

_CONNECTOR_PATTERNS: dict[str, dict[str, str]] = {
    "ingestion": {
        "FIVETRAN": "etl",
        "AIRBYTE": "etl",
        "STITCH": "etl",
        "AIRFLOW": "orchestrator",
        "DAGSTER": "orchestrator",
        "MELTANO": "etl",
    },
    "transformation": {
        "DBT": "transformer",
        "MATILLION": "transformer",
    },
    "consumption": {
        "LOOKER": "bi_tool",
        "SIGMA": "bi_tool",
        "TABLEAU": "bi_tool",
        "POWERBI": "bi_tool",
        "METABASE": "bi_tool",
    },
}

_SIZE_MAP = {
    "X-Small": "XSMALL",
    "Small": "SMALL",
    "Medium": "MEDIUM",
    "Large": "LARGE",
    "X-Large": "XLARGE",
}


def _detect_connectors(service_accounts: list[dict], category: str) -> list[dict]:
    """Match user/role names from service account patterns against known connector patterns."""
    patterns = _CONNECTOR_PATTERNS.get(category, {})
    detected = []
    seen = set()
    for entry in service_accounts:
        name = entry.get("user_name", "") or entry.get("role_name", "")
        for keyword, conn_type in patterns.items():
            if keyword in name.upper() and keyword not in seen:
                seen.add(keyword)
                detected.append({"keyword": keyword, "type": conn_type, "source_name": name})
    return detected


# ---------------------------------------------------------------------------
# Interview sections
# ---------------------------------------------------------------------------

def _section_context(brownfield_context: dict | None) -> dict:
    """Section 1: Context — purpose, team size, maturity target."""
    _section_header("Section 1 — Context")

    # Brownfield audit summary
    if brownfield_context:
        _section_header("Audit Summary (from survey data)")
        warehouses = brownfield_context.get("1_4_warehouse_inventory", {}).get("warehouses", [])
        users = brownfield_context.get("1_2_user_inventory", {}).get("users", [])
        direct_grants = brownfield_context.get("1_3_direct_grants", {}).get("direct_grants", [])
        service_accounts = brownfield_context.get("1_8_service_account_patterns", {}).get("user_query_volume", [])
        tag_refs = brownfield_context.get("1_6_tag_coverage", {}).get("tag_references", [])
        monitors = brownfield_context.get("1_5_resource_monitor_coverage", {}).get("warehouses", [])
        roles = brownfield_context.get("1_1_role_inventory", {}).get("roles", [])
        accountadmin_count = sum(
            1 for r in roles if r.get("name") == "ACCOUNTADMIN" and r.get("assigned_to_users", 0) > 0
        )
        click.echo(f"  Warehouses found     : {len(warehouses)}")
        click.echo(f"  Users found          : {len(users)}")
        click.echo(f"  ACCOUNTADMIN holders : {accountadmin_count}")
        click.echo(f"  Direct grants        : {len(direct_grants)}")
        click.echo(f"  Service accounts     : {len(service_accounts)}")
        click.echo(f"  Tag references       : {len(tag_refs)}")
        click.echo(f"  Resource monitors    : {len(monitors)}")
        click.echo("")

    purpose = _prompt(
        "Primary purpose of this Snowflake environment",
        type=click.Choice(
            ["analytics_bi", "data_platform", "product_analytics", "operational", "mixed"],
            case_sensitive=False,
        ),
        default="data_platform",
    )

    click.echo("\n  Team size:")
    de_count = _prompt("  Data engineers", type=int, default=2)
    analyst_count = _prompt("  Analysts / BI users", type=int, default=5)
    ds_count = _prompt("  Data scientists", type=int, default=0)
    sa_count = _prompt("  Service accounts (integrations)", type=int, default=3)

    maturity = _prompt(
        "Maturity target",
        type=click.Choice(["core", "observability", "enforcement"], case_sensitive=False),
        default="core",
    )
    _note("If unsure, start with core — structure first, enforcement second.")

    return {
        "purpose": purpose,
        "team": {
            "data_engineers": de_count,
            "analysts": analyst_count,
            "data_scientists": ds_count,
            "service_accounts": sa_count,
        },
        "maturity_target": maturity,
    }


def _section_ingestion(brownfield_context: dict | None) -> list[dict]:
    """Section 2: Ingestion — one connector per tool."""
    _section_header("Section 2 — Ingestion (LOADER layer)")
    _note("Each tool gets its own connector role. See PHILOSOPHY.md §Connector Role Philosophy.")

    # Brownfield: detect connectors from service account patterns
    if brownfield_context:
        service_accounts = brownfield_context.get("1_8_service_account_patterns", {}).get("user_query_volume", [])
        detected = _detect_connectors(service_accounts, "ingestion")
        if detected:
            click.echo(click.style(
                f"  Detected {len(detected)} possible ingestion connector(s) from audit data:", fg="cyan"
            ))
            for d in detected:
                click.echo(f"    {d['keyword']} ({d['type']}) — found as '{d['source_name']}'")

    connectors = []
    while True:
        click.echo("")
        if not _confirm("Add an ingestion tool?", default=True if not connectors else False):
            break

        raw_name = _prompt("  Integration name (uppercase, e.g. FIVETRAN)")
        name = _normalize_identifier("  Integration name (uppercase, e.g. FIVETRAN)", raw_name)

        itype = _prompt(
            "  Type",
            type=click.Choice(["etl", "orchestrator", "event_stream", "custom"], case_sensitive=False),
        )
        target_db = _prompt(f"  Target database (e.g. RAW_{name})").upper()

        all_schemas = _confirm("  Write to all schemas in that database?", default=True)
        if all_schemas:
            target_schemas = ["*"]
        else:
            schemas_input = _prompt("  Target schemas (comma-separated)")
            target_schemas = [s.strip().upper() for s in schemas_input.split(",")]

        click.echo("  Privileges needed:")
        needs_insert = _confirm("    INSERT?", default=True)
        needs_create_table = _confirm("    CREATE TABLE?", default=True)
        needs_select = _confirm("    SELECT (read-back for incremental)?", default=False)
        privileges = []
        if needs_insert:
            privileges.append("INSERT")
        if needs_create_table:
            privileges.append("CREATE TABLE")
        if needs_select:
            privileges.append("SELECT")

        extra_grants: list[str] = []
        if itype == "event_stream":
            if _confirm("  Snowpipe integration? (needs CREATE PIPE, MONITOR)", default=True):
                extra_grants = ["CREATE PIPE", "MONITOR"]

        warehouse = _prompt("  Warehouse (INGEST / TRANSFORM / ANALYTICS or custom)").upper()
        reason = _prompt("  One-sentence reason (optional, press Enter to skip)", default="")
        vendor_managed = _confirm("  Vendor-managed credential (e.g. Fivetran, Airbyte)?", default=False)

        entry: dict = {
            "name": name,
            "type": itype,
            "target_db": target_db,
            "target_schemas": target_schemas,
            "privileges": privileges,
            "warehouse": warehouse,
            "reason": reason,
            "vendor_managed": vendor_managed,
        }
        if extra_grants:
            entry["extra_grants"] = extra_grants

        connectors.append(entry)
        click.echo(click.style(f"  -> CONN_{name} added", fg="green"))

    return connectors


def _section_transformation(brownfield_context: dict | None) -> list[dict]:
    """Section 3: Transformation — dbt / other."""
    _section_header("Section 3 — Transformation (TRANSFORMER layer)")

    # Brownfield: detect transformation connectors
    if brownfield_context:
        service_accounts = brownfield_context.get("1_8_service_account_patterns", {}).get("user_query_volume", [])
        detected = _detect_connectors(service_accounts, "transformation")
        if detected:
            click.echo(click.style(
                f"  Detected {len(detected)} possible transformation connector(s) from audit data:", fg="cyan"
            ))
            for d in detected:
                click.echo(f"    {d['keyword']} ({d['type']}) — found as '{d['source_name']}'")

    connectors = []
    while True:
        click.echo("")
        prompt_text = "Add a transformation tool?" if not connectors else "Add another transformation tool?"
        if not _confirm(prompt_text, default=True if not connectors else False):
            break

        tool = _prompt(
            "Transformation tool",
            type=click.Choice(["dbt_core", "dbt_cloud", "custom_python_sql", "spark", "other"], case_sensitive=False),
        )
        raw_name = _prompt("Connector name (uppercase, e.g. DBT_PROD)")
        name = _normalize_identifier("Connector name (uppercase, e.g. DBT_PROD)", raw_name)

        source_input = _prompt("Source databases (comma-separated, e.g. RAW_FIVETRAN,RAW_AIRFLOW)")
        source_dbs = [s.strip().upper() for s in source_input.split(",")]

        target_db = _prompt("Target database (e.g. ANALYTICS)").upper()

        dynamic_schemas = _confirm("Does it create schemas dynamically?", default=True)
        _note("If yes, CREATE SCHEMA privilege is required on the target database.")

        privileges = ["SELECT", "INSERT", "CREATE TABLE"]
        if dynamic_schemas:
            privileges.append("CREATE SCHEMA")

        warehouse = _prompt("Warehouse (typically TRANSFORM)").upper()
        reason = _prompt("One-sentence reason (optional, press Enter to skip)", default="")

        connectors.append({
            "name": name,
            "type": "transformer",
            "source_dbs": source_dbs,
            "target_db": target_db,
            "target_schemas": ["*"],
            "privileges": privileges,
            "warehouse": warehouse,
            "reason": reason,
            "vendor_managed": False,
        })
        click.echo(click.style(f"  -> CONN_{name} added", fg="green"))

    return connectors


def _section_consumption(brownfield_context: dict | None) -> list[dict]:
    """Section 4: Consumption — BI tools / analyst access."""
    _section_header("Section 4 — Consumption (ANALYST layer)")

    # Brownfield: detect consumption connectors
    if brownfield_context:
        service_accounts = brownfield_context.get("1_8_service_account_patterns", {}).get("user_query_volume", [])
        detected = _detect_connectors(service_accounts, "consumption")
        if detected:
            click.echo(click.style(
                f"  Detected {len(detected)} possible consumption connector(s) from audit data:", fg="cyan"
            ))
            for d in detected:
                click.echo(f"    {d['keyword']} ({d['type']}) — found as '{d['source_name']}'")

    connectors = []
    while True:
        click.echo("")
        if not _confirm("Add a BI tool or consumer?", default=True if not connectors else False):
            break

        raw_name = _prompt("  Tool name (uppercase, e.g. LOOKER)")
        name = _normalize_identifier("  Tool name (uppercase, e.g. LOOKER)", raw_name)
        source_db = _prompt("  Source database (read-only, e.g. MARTS)").upper()

        all_schemas = _confirm("  Access all schemas?", default=True)
        target_schemas = ["*"] if all_schemas else [
            s.strip().upper()
            for s in _prompt("  Schemas (comma-separated)").split(",")
        ]

        warehouse = _prompt("  Warehouse (typically ANALYTICS)").upper()
        reason = _prompt("  One-sentence reason (optional, press Enter to skip)", default="")
        vendor_managed = _confirm("  Vendor-managed credential?", default=True)

        connectors.append({
            "name": name,
            "type": "bi_tool",
            "source_db": source_db,
            "target_schemas": target_schemas,
            "privileges": ["SELECT"],
            "warehouse": warehouse,
            "reason": reason,
            "vendor_managed": vendor_managed,
        })
        click.echo(click.style(f"  -> CONN_{name} added", fg="green"))

    return connectors


def _section_warehouses(brownfield_context: dict | None = None) -> dict:
    """Section 5: Warehouse topology — sizes and budgets."""
    _section_header("Section 5 — Warehouse Topology")
    _note("Default: WH_INGEST, WH_TRANSFORM, WH_ANALYTICS. One per workload.")

    # Brownfield: show existing warehouses
    if brownfield_context:
        existing = brownfield_context.get("1_4_warehouse_inventory", {}).get("warehouses", [])
        if existing:
            click.echo(click.style(f"\n  Found {len(existing)} existing warehouse(s) in your environment:", fg="cyan"))
            for wh in existing:
                size = _SIZE_MAP.get(wh.get("size", ""), wh.get("size", "?"))
                click.echo(f"    {wh.get('name', '?')} ({size})")

    sizes = click.Choice(["XSMALL", "SMALL", "MEDIUM", "LARGE"], case_sensitive=False)
    warehouses: dict[str, dict] = {}

    defaults = [("INGEST", "XSMALL", 100), ("TRANSFORM", "XSMALL", 500), ("ANALYTICS", "XSMALL", 150)]
    for wh_name, default_size, default_budget in defaults:
        click.echo(f"\n  WH_{wh_name}:")
        size = _prompt(f"    Size", type=sizes, default=default_size)
        auto_suspend = _prompt(f"    Auto-suspend (minutes)", type=int, default=5)
        budget = _prompt(f"    Monthly credit budget", type=int, default=default_budget)
        if wh_name == "TRANSFORM":
            _note("dbt on SMALL typically uses 50-150 credits/day depending on model count.")
        warehouses[wh_name] = {
            "size": size.upper(),
            "auto_suspend_minutes": auto_suspend,
            "monthly_credit_quota": budget,
            "notify_at_percentage": 75,
            "suspend_at_percentage": 100,
        }

    extra = _confirm("\nAdd additional warehouses (beyond the three defaults)?", default=False)
    if extra:
        while True:
            if not _confirm("Add another warehouse?", default=False):
                break
            raw_name = _prompt("  Warehouse name (without WH_ prefix)")
            wh_name = _normalize_identifier("  Warehouse name (without WH_ prefix)", raw_name)
            size = _prompt("  Size", type=sizes, default="XSMALL")
            auto_suspend = _prompt("  Auto-suspend (minutes)", type=int, default=5)
            budget = _prompt("  Monthly credit budget", type=int, default=100)
            warehouses[wh_name] = {
                "size": size.upper(),
                "auto_suspend_minutes": auto_suspend,
                "monthly_credit_quota": budget,
                "notify_at_percentage": 75,
                "suspend_at_percentage": 100,
            }

    return warehouses


def _section_team(brownfield_context: dict | None = None) -> list[dict]:
    """Section 6: Team Structure — human functional role personas."""
    _section_header("Section 6 — Team Structure")
    _note("Each persona maps to a functional role. Service accounts belong in connectors.yaml.")

    # Brownfield: suggest personas from existing role names
    if brownfield_context:
        human_assignments = brownfield_context.get("1_3_human_role_assignments", {}).get("human_role_assignments", [])
        if human_assignments:
            click.echo(click.style(
                f"\n  Found {len(human_assignments)} human role assignment(s) in your environment:", fg="cyan"
            ))
            for a in human_assignments[:5]:
                click.echo(f"    {a.get('user_name', '?')} -> {a.get('role_name', '?')}")
            if len(human_assignments) > 5:
                click.echo(f"    ... and {len(human_assignments) - 5} more")

    default_personas = ["DATA_ENGINEER", "DATA_ANALYST", "BI_DEVELOPER", "DATA_SCIENTIST"]
    click.echo("\n  Default personas: " + ", ".join(default_personas))
    use_defaults = _confirm("Start with the default personas?", default=True)

    personas: list[str] = list(default_personas) if use_defaults else []

    if use_defaults:
        for persona in default_personas:
            if not _confirm(f"  Include {persona}?", default=True):
                personas.remove(persona)

    while True:
        if not _confirm("Add a custom persona?", default=False):
            break
        name = _prompt("  Persona name (uppercase)").upper()
        personas.append(name)

    default_wh = {
        "DATA_ENGINEER": "TRANSFORM",
        "DATA_ANALYST": "ANALYTICS",
        "BI_DEVELOPER": "ANALYTICS",
        "DATA_SCIENTIST": "ANALYTICS",
    }

    functional_roles = []
    for persona_name in personas:
        click.echo(click.style(f"\n  --- {persona_name} ---", bold=True))

        wh_input = _prompt(
            f"  Warehouse for {persona_name} (INGEST / TRANSFORM / ANALYTICS or custom)",
            default=default_wh.get(persona_name, "ANALYTICS"),
        ).upper()

        db_entries: list[dict] = []
        click.echo(f"  Database access for {persona_name}:")
        while True:
            prompt_default = not db_entries  # default True for first entry, False after
            if not _confirm("  Add a database access entry?", default=prompt_default):
                break

            db = _prompt("    Database name (uppercase)").upper()

            all_schemas = _confirm("    All schemas?", default=True)
            if all_schemas:
                schemas = ["*"]
                scope_to = None
            else:
                schemas_input = _prompt("    Named schemas (comma-separated)")
                named_schemas = [s.strip().upper() for s in schemas_input.split(",")]
                schemas = ["*"]  # always wildcard for greenfield safety
                scope_to = named_schemas

            # Privilege collection with confirmation loop
            while True:
                click.echo("    Privileges:")
                privs: list[str] = []
                if _confirm("      SELECT?", default=True):
                    privs.append("SELECT")
                if _confirm("      INSERT?", default=False):
                    privs.append("INSERT")
                if _confirm("      CREATE TABLE?", default=False):
                    privs.append("CREATE TABLE")
                if _confirm("      CREATE SCHEMA?", default=False):
                    privs.append("CREATE SCHEMA")
                privs_display = ", ".join(privs) if privs else "NONE"
                if _confirm(f"      -> {db}: {privs_display} — correct?", default=True):
                    break

            entry_reason = _prompt("    Reason (optional, press Enter to skip)", default="")

            entry: dict = {
                "db": db,
                "schemas": schemas,
                "privileges": privs,
                "reason": entry_reason,
            }
            if scope_to:
                entry["scope_to"] = scope_to

            db_entries.append(entry)
            click.echo(click.style(f"    -> {db} added", fg="green"))

        role_reason = _prompt(f"  Role-level reason for {persona_name}")

        functional_roles.append({
            "name": persona_name,
            "warehouse": wh_input,
            "database_access": db_entries,
            "reason": role_reason,
        })
        click.echo(click.style(f"  -> {persona_name} added", fg="green"))

    return functional_roles


def _section_tags(brownfield_context: dict | None = None) -> dict:
    """Section 7: Tagging taxonomy."""
    _section_header("Section 7 — Tagging")
    _note("Tags are defined now and enforced at Observability expansion.")

    # Brownfield: show existing tags
    if brownfield_context:
        tag_refs = brownfield_context.get("1_6_tag_coverage", {}).get("tag_references", [])
        if tag_refs:
            click.echo(click.style(f"\n  Found {len(tag_refs)} tag reference(s) in your environment:", fg="cyan"))
            for t in tag_refs[:5]:
                click.echo(f"    {t.get('tag_name', '?')} on {t.get('object_name', '?')}")

    cost_center_label = "Cost center tag values (comma-separated, e.g. engineering,analytics,product)"
    cost_center_raw = _prompt(
        cost_center_label,
        default="engineering,analytics,product,infrastructure",
    )
    cost_center_values = _validate_tag_values(cost_center_label, cost_center_raw, min_count=2)

    env_label = "Environment tag values (comma-separated)"
    env_raw = _prompt(env_label, default="prod,staging,dev")
    env_values = _validate_tag_values(env_label, env_raw, min_count=2)

    pii_required = _confirm("Include PII tag (for column-level classification)?", default=True)
    sensitivity_required = _confirm("Include sensitivity tag (public/internal/confidential/restricted)?", default=True)

    required_tags = [
        {"name": "cost_center", "values": cost_center_values, "apply_to": ["database", "schema", "warehouse"]},
        {"name": "environment", "values": env_values, "apply_to": ["database", "schema", "warehouse"]},
        {"name": "owner", "values": [], "apply_to": ["database", "schema"]},
    ]

    # Custom required tags
    while _confirm("Add a custom required tag?", default=False):
        tag_name = _prompt("  Tag name").lower().replace(" ", "_")
        values_label = "  Allowed values (comma-separated)"
        values_raw = _prompt(values_label)
        values = _validate_tag_values(values_label, values_raw, min_count=1)
        apply_input = _prompt("  Apply to (comma-separated, e.g. database,schema,warehouse,table,column)")
        apply_to = [a.strip().lower() for a in apply_input.split(",") if a.strip()]
        required_tags.append({"name": tag_name, "values": values, "apply_to": apply_to})
        click.echo(click.style(f"  -> tag '{tag_name}' added", fg="green"))

    optional_tags = [{"name": "project", "apply_to": ["schema", "table"]}]
    if sensitivity_required:
        optional_tags.append({
            "name": "sensitivity",
            "values": ["public", "internal", "confidential", "restricted"],
            "apply_to": ["database", "schema", "table"],
        })
    if pii_required:
        optional_tags.append({
            "name": "pii",
            "values": ["true", "false"],
            "apply_to": ["table", "column"],
        })

    return {"required_tags": required_tags, "optional_tags": optional_tags, "enforcement_stage": "core"}


def _section_emergency_access(brownfield_context: dict | None = None) -> dict:
    """Section 8: FIREFIGHTER emergency access."""
    _section_header("Section 8 — Emergency Access (FIREFIGHTER)")
    _note("FIREFIGHTER is a dormant role. It must have an explicit activation gate.")

    # Brownfield: check if FIREFIGHTER role already exists
    if brownfield_context:
        roles = brownfield_context.get("1_1_role_inventory", {}).get("roles", [])
        ff_role = next((r for r in roles if "FIREFIGHTER" in r.get("name", "").upper()), None)
        if ff_role:
            click.echo(click.style(
                f"  Found existing FIREFIGHTER-type role: {ff_role['name']}", fg="cyan"
            ))
        else:
            _note("No FIREFIGHTER role found in current environment — this will be created.")

    contacts = []
    click.echo("\n  Authorized FIREFIGHTER activators:")
    while True:
        if not _confirm("  Add an authorized contact?", default=True if not contacts else False):
            break
        name = _prompt("    Name")
        title = _prompt("    Title")
        contact = _prompt("    Contact (email or Slack handle)")
        contacts.append({"name": name, "title": title, "contact": contact})

    notification = _prompt(
        "Notification process when FIREFIGHTER is activated (e.g. #incidents Slack channel)"
    )
    deactivation_sla = _prompt(
        "Deactivation SLA",
        type=click.Choice(["same_day", "within_24h", "per_incident"], case_sensitive=False),
        default="within_24h",
    )

    return {
        "authorized_contacts": contacts,
        "notification_process": notification,
        "deactivation_sla": deactivation_sla,
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _write_connectors_yaml(connectors: list[dict], output_dir: Path):
    path = output_dir / "connectors.yaml"
    content = "# intake/connectors.yaml\n"
    content += "# Generated by scripts/intake_interview.py\n"
    content += "# See: docs/SPEC.md §1.2, docs/PHILOSOPHY.md §The Connector Role Philosophy\n\n"
    content += yaml.dump({"connectors": connectors}, default_flow_style=False, sort_keys=False)
    path.write_text(content)
    return path


def _write_team_yaml(functional_roles: list[dict], output_dir: Path, emergency: dict | None = None):
    path = output_dir / "team.yaml"
    content = "# intake/team.yaml\n"
    content += "# Generated by scripts/intake_interview.py\n"
    content += "# See: docs/SPEC.md §1.4 — Team structure and functional roles\n"
    content += "# scope_to: when named schemas were specified, schemas is set to [\"*\"] for greenfield\n"
    content += "#   safety; update schemas: to the scope_to list once those schemas exist.\n\n"
    doc: dict = {"functional_roles": functional_roles}
    if emergency:
        doc["emergency_access"] = emergency
    content += yaml.dump(doc, default_flow_style=False, sort_keys=False)
    path.write_text(content)
    return path


def _write_tags_yaml(tags: dict, output_dir: Path):
    path = output_dir / "tags.yaml"
    content = "# intake/tags.yaml\n"
    content += "# Generated by scripts/intake_interview.py\n"
    content += "# See: docs/SPEC.md §1.3, docs/PHILOSOPHY.md §The Maturity Model\n\n"
    content += yaml.dump(tags, default_flow_style=False, sort_keys=False)
    path.write_text(content)
    return path


def _write_decisions_md(
    context: dict,
    warehouse_config: dict,
    emergency: dict,
    output_dir: Path,
    mode: str,
    connectors: list[dict] | None = None,
    team_roles: list[dict] | None = None,
    tags: dict | None = None,
    author: str = "",
):
    path = output_dir / "decisions.md"
    connectors = connectors or []
    team_roles = team_roles or []
    tags = tags or {}

    lines = [
        "# Governance Decision Log",
        "*Flynn Data Services — Generated during intake*",
        "",
        "---",
        "",
        "## Environment Context",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Purpose | {context['purpose']} |",
        f"| Data engineers | {context['team']['data_engineers']} |",
        f"| Analysts | {context['team']['analysts']} |",
        f"| Data scientists | {context['team']['data_scientists']} |",
        f"| Service accounts | {context['team']['service_accounts']} |",
        f"| Maturity target | {context['maturity_target']} |",
        f"| Intake mode | {mode} |",
        "",
        "---",
        "",
        "## Decisions",
        "",
        "| Decision | Options considered | Choice made | Reason | Source | Reference |",
        "|----------|-------------------|-------------|--------|--------|-----------|",
        "| Database structure | Per-source vs shared RAW | Per-source | Stronger isolation — each connector scoped to its own DB | FDS standard | PHILOSOPHY.md §Connector Role Philosophy |",
        f"| Maturity target | Core / Observability / Enforcement | {context['maturity_target'].capitalize()} | Structure first, enforcement second | Client decision | PHILOSOPHY.md §The Maturity Model |",
        "| Service account auth | Password vs key-pair | Key-pair (RSA) | Audit trail + rotation safety | FDS standard | PHILOSOPHY.md §Core Principles #8 |",
        "| Connector role pattern | Functional roles only vs connector layer | Connector layer | LOADER is too broad | FDS standard | PHILOSOPHY.md §Connector Role Philosophy |",
    ]

    # Dynamic warehouse topology row
    wh_names = list(warehouse_config.keys())
    default_3 = set(wh_names) == {"INGEST", "TRANSFORM", "ANALYTICS"}
    wh_choice = "3 standard workload warehouses (default)" if default_3 else f"Custom: {', '.join(f'WH_{n}' for n in wh_names)}"
    wh_source = "FDS standard" if default_3 else "Client decision"
    lines.append(
        f"| Warehouse topology | Single shared vs workload-separated | {wh_choice} | Noisy neighbor rule | {wh_source} | PHILOSOPHY.md §Warehouse Isolation Standard |"
    )

    # Dynamic connector row
    if connectors:
        types = ", ".join(sorted({c["type"] for c in connectors}))
        lines.append(
            f"| Connector count | N/A | {len(connectors)} connector(s) ({types}) | As defined in intake | Client decision | connectors.yaml |"
        )

    # Dynamic persona row
    if team_roles:
        names = ", ".join(r["name"] for r in team_roles)
        lines.append(
            f"| Functional personas | N/A | {len(team_roles)} persona(s): {names} | As defined in intake | Client decision | team.yaml |"
        )

    # Dynamic tag row
    required = tags.get("required_tags", [])
    if required:
        tag_names = ", ".join(t["name"] for t in required)
        lines.append(
            f"| Required tags | N/A | {len(required)} tag(s): {tag_names} | Taxonomy defined during intake | Client decision | tags.yaml |"
        )

    lines += [
        "",
        "---",
        "",
        "## Emergency Access (FIREFIGHTER)",
        "",
        "| Name | Title | Contact |",
        "|------|-------|---------|",
    ]
    for c in emergency.get("authorized_contacts", []):
        lines.append(f"| {c['name']} | {c['title']} | {c['contact']} |")

    lines += [
        "",
        f"**Notification process:** {emergency.get('notification_process', 'TBD')}",
        "",
        f"**Deactivation SLA:** {emergency.get('deactivation_sla', 'TBD')}",
        "",
        "---",
        "",
        "## Warehouse Topology",
        "",
        "| Warehouse | Size | Auto-suspend | Monthly credits | Notify at | Suspend at |",
        "|-----------|------|-------------|-----------------|-----------|------------|",
    ]
    for wh_name, cfg in warehouse_config.items():
        lines.append(
            f"| WH_{wh_name} | {cfg['size']} | {cfg['auto_suspend_minutes']}m "
            f"| {cfg['monthly_credit_quota']} | {cfg['notify_at_percentage']}% | {cfg['suspend_at_percentage']}% |"
        )

    today = datetime.date.today().isoformat()
    author_display = author if author else ""
    lines += [
        "",
        "---",
        "",
        "## Change Log",
        "",
        "| Date | Change | Author |",
        "|------|--------|--------|",
        f"| {today} | Initial intake | {author_display} |",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


def _validate_connectors(connectors: list[dict]) -> list[str]:
    """Basic validation of connector entries."""
    errors = []
    valid_types = {"etl", "orchestrator", "event_stream", "transformer", "bi_tool", "custom"}
    valid_privs = {"SELECT", "INSERT", "CREATE TABLE", "CREATE SCHEMA", "CREATE PIPE", "MONITOR", "USAGE"}
    seen_names = set()

    for i, c in enumerate(connectors):
        prefix = f"Connector[{i}] {c.get('name', '?')}"
        if not c.get("name"):
            errors.append(f"{prefix}: missing 'name'")
        if c.get("name") in seen_names:
            errors.append(f"{prefix}: duplicate name")
        seen_names.add(c.get("name"))

        if c.get("type") not in valid_types:
            errors.append(f"{prefix}: invalid type '{c.get('type')}' — must be one of {valid_types}")

        if not c.get("warehouse"):
            errors.append(f"{prefix}: missing 'warehouse'")

        for priv in c.get("privileges", []):
            if priv not in valid_privs:
                errors.append(f"{prefix}: unrecognized privilege '{priv}'")

    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option("--greenfield", "mode", flag_value="greenfield", default=True, help="Full greenfield interview")
@click.option("--brownfield", "mode", flag_value="brownfield", help="Brownfield — pre-populate from audit output")
@click.option("--output-dir", default="intake", show_default=True, help="Output directory for generated files")
@click.option("--dry-run", is_flag=True, help="Print generated YAML to stdout; skip file writes")
def cli(mode: str, output_dir: str, dry_run: bool):
    """Interactive intake interview — generates connectors.yaml, team.yaml, tags.yaml, decisions.md."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    click.echo(click.style("\nFDS Snowflake Governance — Intake Interview", bold=True, fg="cyan"))
    click.echo(click.style(f"Mode: {mode.upper()}", fg="cyan"))
    click.echo("This interview generates connectors.yaml, tags.yaml, and decisions.md.")
    click.echo("Tip: run /intake-greenfield or /intake-review in Claude Code for a guided session.\n")

    # Load brownfield context if available
    brownfield_context: dict | None = None
    if mode == "brownfield":
        survey_dir = Path("intake/survey_output")
        if not survey_dir.exists():
            click.echo(click.style(
                "WARNING: intake/survey_output/ not found. Run 'uv run scripts/audit.py audit' first.",
                fg="yellow",
            ))
        else:
            brownfield_context = {}
            for f in survey_dir.glob("*.json"):
                try:
                    brownfield_context[f.stem] = json.loads(f.read_text())
                except Exception:
                    pass
            click.echo(f"Loaded {len(brownfield_context)} audit sections from {survey_dir}")

    # State file — offer resume if a prior session was interrupted
    existing_state = _load_state(out_dir)
    data: dict = {}
    completed_sections: set[str] = set()

    if existing_state and existing_state.get("mode") == mode:
        prior = existing_state.get("completed_sections", [])
        if prior:
            click.echo(click.style(
                f"\nFound an interrupted session (completed: {', '.join(prior)}).", fg="yellow"
            ))
            choice = _prompt(
                "Resume, restart, or abort?",
                type=click.Choice(["resume", "restart", "abort"], case_sensitive=False),
                default="resume",
            )
            if choice == "abort":
                click.echo("Aborted.")
                sys.exit(0)
            elif choice == "resume":
                data = existing_state.get("data", {})
                completed_sections = set(prior)
                click.echo(click.style("Resuming from last completed section.", fg="cyan"))
            else:
                _delete_state(out_dir)

    def _run_section(section_id: str, fn, *args) -> Any:
        """Run a section or load from state if already completed."""
        if section_id in completed_sections:
            click.echo(click.style(f"  [resumed] Skipping {section_id} (already completed)", fg="cyan"))
            return data[section_id]
        result = fn(*args)
        data[section_id] = result
        completed_sections.add(section_id)
        _save_state({
            "version": 1,
            "mode": mode,
            "completed_sections": list(completed_sections),
            "data": data,
            "timestamp": datetime.datetime.now().isoformat(),
        }, out_dir)
        return result

    # Run interview sections
    context = _run_section("context", _section_context, brownfield_context)
    ingestion_connectors = _run_section("ingestion", _section_ingestion, brownfield_context)
    transformation_connectors = _run_section("transformation", _section_transformation, brownfield_context)
    consumption_connectors = _run_section("consumption", _section_consumption, brownfield_context)
    all_connectors = ingestion_connectors + transformation_connectors + consumption_connectors
    warehouse_config = _run_section("warehouses", _section_warehouses, brownfield_context)
    team_roles = _run_section("team", _section_team, brownfield_context)
    tags = _run_section("tags", _section_tags, brownfield_context)
    emergency = _run_section("emergency", _section_emergency_access, brownfield_context)

    # Author for decision log
    author_name = _prompt("Your name (for the decision log)", default="")

    # Validate
    _section_header("Validation")
    errors = _validate_connectors(all_connectors)
    if errors:
        click.echo(click.style("Validation errors:", fg="red"))
        for e in errors:
            click.echo(f"  - {e}")
        if not _confirm("Continue despite validation errors?", default=False):
            click.echo("Aborted.")
            sys.exit(1)
    else:
        click.echo(click.style("  All connectors valid.", fg="green"))

    # Preview — connectors
    _section_header("Preview — connectors.yaml")
    click.echo(f"  {len(all_connectors)} connector(s):")
    for c in all_connectors:
        click.echo(f"    CONN_{c['name']} ({c['type']}) -> {c.get('target_db', c.get('source_db', '?'))} on WH_{c['warehouse']}")

    # Preview — team
    _section_header("Preview — team.yaml")
    click.echo(f"  {len(team_roles)} persona(s):")
    for r in team_roles:
        click.echo(f"    {r['name']} -> WH_{r['warehouse']}, {len(r['database_access'])} DB(s)")

    # Preview — tags
    _section_header("Preview — tags.yaml")
    click.echo(f"  {len(tags.get('required_tags', []))} required tag(s):")
    for t in tags.get("required_tags", []):
        click.echo(f"    {t['name']}: {len(t.get('values', []))} values, applies to {', '.join(t.get('apply_to', []))}")

    # Dry-run: print to stdout and exit
    if dry_run:
        click.echo(click.style("\n--- DRY RUN: connectors.yaml ---", bold=True))
        click.echo(yaml.dump({"connectors": all_connectors}, default_flow_style=False, sort_keys=False))
        click.echo(click.style("--- DRY RUN: team.yaml ---", bold=True))
        team_doc: dict = {"functional_roles": team_roles}
        if emergency:
            team_doc["emergency_access"] = emergency
        click.echo(yaml.dump(team_doc, default_flow_style=False, sort_keys=False))
        click.echo(click.style("--- DRY RUN: tags.yaml ---", bold=True))
        click.echo(yaml.dump(tags, default_flow_style=False, sort_keys=False))
        click.echo(click.style("--- END DRY RUN ---", bold=True))
        sys.exit(0)

    if not _confirm("\nWrite output files?", default=True):
        click.echo("Aborted — no files written.")
        sys.exit(0)

    # Write outputs
    c_path = _write_connectors_yaml(all_connectors, out_dir)
    tm_path = _write_team_yaml(team_roles, out_dir, emergency)
    t_path = _write_tags_yaml(tags, out_dir)
    d_path = _write_decisions_md(
        context, warehouse_config, emergency, out_dir, mode,
        connectors=all_connectors, team_roles=team_roles, tags=tags, author=author_name,
    )

    # Clean up state file on success
    _delete_state(out_dir)

    click.echo("")
    click.echo(click.style("Files written:", bold=True))
    click.echo(f"  {c_path}")
    click.echo(f"  {tm_path}")
    click.echo(f"  {t_path}")
    click.echo(f"  {d_path}")
    click.echo("")
    click.echo("Next: run 'uv run scripts/generate_tf.py' to generate Terraform variables.")


if __name__ == "__main__":
    cli()

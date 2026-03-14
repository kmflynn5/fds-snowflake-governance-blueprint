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

Outputs:
    intake/connectors.yaml
    intake/tags.yaml
    intake/decisions.md
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Interview sections
# ---------------------------------------------------------------------------

def _section_context(brownfield_context: dict | None) -> dict:
    """Section 1: Context — purpose, team size, maturity target."""
    _section_header("Section 1 — Context")

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

    connectors = []
    while True:
        click.echo("")
        if not _confirm("Add an ingestion tool?", default=True if not connectors else False):
            break

        name = _prompt("  Integration name (uppercase, e.g. FIVETRAN)").upper()
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
        reason = _prompt("  One-sentence reason for this connector")
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

    connectors = []
    if not _confirm("Add a transformation tool?", default=True):
        return connectors

    tool = _prompt(
        "Transformation tool",
        type=click.Choice(["dbt_core", "dbt_cloud", "custom_python_sql", "spark", "other"], case_sensitive=False),
    )
    name = _prompt("Connector name (uppercase, e.g. DBT_PROD)").upper()

    source_input = _prompt("Source databases (comma-separated, e.g. RAW_FIVETRAN,RAW_AIRFLOW)")
    source_dbs = [s.strip().upper() for s in source_input.split(",")]

    target_db = _prompt("Target database (e.g. ANALYTICS)").upper()

    dynamic_schemas = _confirm("Does it create schemas dynamically?", default=True)
    _note("If yes, CREATE SCHEMA privilege is required on the target database.")

    privileges = ["SELECT", "INSERT", "CREATE TABLE"]
    if dynamic_schemas:
        privileges.append("CREATE SCHEMA")

    warehouse = _prompt("Warehouse (typically TRANSFORM)").upper()
    reason = _prompt("One-sentence reason for this connector")

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

    connectors = []
    while True:
        click.echo("")
        if not _confirm("Add a BI tool or consumer?", default=True if not connectors else False):
            break

        name = _prompt("  Tool name (uppercase, e.g. LOOKER)").upper()
        source_db = _prompt("  Source database (read-only, e.g. MARTS)").upper()

        all_schemas = _confirm("  Access all schemas?", default=True)
        target_schemas = ["*"] if all_schemas else [
            s.strip().upper()
            for s in _prompt("  Schemas (comma-separated)").split(",")
        ]

        warehouse = _prompt("  Warehouse (typically ANALYTICS)").upper()
        reason = _prompt("  One-sentence reason")
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


def _section_warehouses() -> dict:
    """Section 5: Warehouse topology — sizes and budgets."""
    _section_header("Section 5 — Warehouse Topology")
    _note("Default: WH_INGEST, WH_TRANSFORM, WH_ANALYTICS. One per workload.")

    sizes = click.Choice(["XSMALL", "SMALL", "MEDIUM", "LARGE"], case_sensitive=False)
    warehouses: dict[str, dict] = {}

    defaults = [("INGEST", "XSMALL", 100), ("TRANSFORM", "XSMALL", 200), ("ANALYTICS", "XSMALL", 150)]
    for wh_name, default_size, default_budget in defaults:
        click.echo(f"\n  WH_{wh_name}:")
        size = _prompt(f"    Size", type=sizes, default=default_size)
        auto_suspend = _prompt(f"    Auto-suspend (minutes)", type=int, default=5)
        budget = _prompt(f"    Monthly credit budget", type=int, default=default_budget)
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
            wh_name = _prompt("  Warehouse name (without WH_ prefix)").upper()
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


def _section_tags() -> dict:
    """Section 7: Tagging taxonomy."""
    _section_header("Section 7 — Tagging")
    _note("Tags are defined now and enforced at Observability expansion.")

    cost_center_values_input = _prompt(
        "Cost center tag values (comma-separated, e.g. engineering,analytics,product)",
        default="engineering,analytics,product,infrastructure",
    )
    cost_center_values = [v.strip().lower() for v in cost_center_values_input.split(",")]

    env_values_input = _prompt(
        "Environment tag values (comma-separated)",
        default="prod,staging,dev",
    )
    env_values = [v.strip().lower() for v in env_values_input.split(",")]

    pii_required = _confirm("Include PII tag (for column-level classification)?", default=True)
    sensitivity_required = _confirm("Include sensitivity tag (public/internal/confidential/restricted)?", default=True)

    required_tags = [
        {"name": "cost_center", "values": cost_center_values, "apply_to": ["database", "schema", "warehouse"]},
        {"name": "environment", "values": env_values, "apply_to": ["database", "schema", "warehouse"]},
        {"name": "owner", "values": [], "apply_to": ["database", "schema"]},
    ]

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


def _section_emergency_access() -> dict:
    """Section 8: FIREFIGHTER emergency access."""
    _section_header("Section 8 — Emergency Access (FIREFIGHTER)")
    _note("FIREFIGHTER is a dormant role. It must have an explicit activation gate.")

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
):
    path = output_dir / "decisions.md"
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
        "| Decision | Options considered | Choice made | Reason | Reference |",
        "|----------|-------------------|-------------|--------|-----------|",
        "| Database structure | Per-source vs shared RAW | Per-source | Stronger isolation — each connector scoped to its own DB | PHILOSOPHY.md §Connector Role Philosophy |",
        f"| Maturity target | Core / Observability / Enforcement | {context['maturity_target'].capitalize()} | Structure first, enforcement second | PHILOSOPHY.md §The Maturity Model |",
        "| Warehouse topology | Single shared vs workload-separated | Workload-separated | Noisy neighbor rule | PHILOSOPHY.md §Warehouse Isolation Standard |",
        "| Service account auth | Password vs key-pair | Key-pair (RSA) | Audit trail + rotation safety | PHILOSOPHY.md §Core Principles #8 |",
        "| Connector role pattern | Functional roles only vs connector layer | Connector layer | LOADER is too broad | PHILOSOPHY.md §Connector Role Philosophy |",
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

    lines += ["", "---", "", "## Change Log", "", "| Date | Change | Author |", "|------|--------|--------|", "| | Initial intake | |"]
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
def cli(mode: str, output_dir: str):
    """Interactive intake interview — generates connectors.yaml, tags.yaml, decisions.md."""
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

    # Run interview sections
    context = _section_context(brownfield_context)
    ingestion_connectors = _section_ingestion(brownfield_context)
    transformation_connectors = _section_transformation(brownfield_context)
    consumption_connectors = _section_consumption(brownfield_context)
    all_connectors = ingestion_connectors + transformation_connectors + consumption_connectors
    warehouse_config = _section_warehouses()
    tags = _section_tags()
    emergency = _section_emergency_access()

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

    # Preview
    _section_header("Preview — connectors.yaml")
    click.echo(f"  {len(all_connectors)} connector(s):")
    for c in all_connectors:
        click.echo(f"    CONN_{c['name']} ({c['type']}) -> {c.get('target_db', c.get('source_db', '?'))} on WH_{c['warehouse']}")

    if not _confirm("\nWrite output files?", default=True):
        click.echo("Aborted — no files written.")
        sys.exit(0)

    # Write outputs
    c_path = _write_connectors_yaml(all_connectors, out_dir)
    t_path = _write_tags_yaml(tags, out_dir)
    d_path = _write_decisions_md(context, warehouse_config, emergency, out_dir, mode)

    click.echo("")
    click.echo(click.style("Files written:", bold=True))
    click.echo(f"  {c_path}")
    click.echo(f"  {t_path}")
    click.echo(f"  {d_path}")
    click.echo("")
    click.echo("Next: run 'uv run scripts/generate_tf.py' to generate Terraform variables.")


if __name__ == "__main__":
    cli()

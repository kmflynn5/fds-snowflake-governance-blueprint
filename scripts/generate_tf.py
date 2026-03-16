"""
scripts/generate_tf.py — Config-to-Terraform codegen

Reads intake/connectors.yaml + intake/tags.yaml and outputs .auto.tfvars.json
files to terraform/ (the root Terraform directory, so they are auto-loaded).

Output files:
    terraform/databases.auto.tfvars.json
    terraform/warehouses.auto.tfvars.json
    terraform/rbac.auto.tfvars.json

Usage:
    uv run scripts/generate_tf.py
    uv run scripts/generate_tf.py --connectors custom/connectors.yaml
    uv run scripts/generate_tf.py --output-dir terraform
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import yaml


# ---------------------------------------------------------------------------
# Derivation logic
# ---------------------------------------------------------------------------

def load_config(connectors_path: str, tags_path: str) -> tuple[list[dict], dict]:
    """Load and return (connectors list, tags dict)."""
    c_path = Path(connectors_path)
    t_path = Path(tags_path)

    if not c_path.exists():
        raise click.ClickException(f"connectors.yaml not found: {c_path}")
    if not t_path.exists():
        raise click.ClickException(f"tags.yaml not found: {t_path}")

    connectors = yaml.safe_load(c_path.read_text())["connectors"]
    tags = yaml.safe_load(t_path.read_text())
    return connectors, tags


def derive_databases(connectors: list[dict]) -> dict:
    """Derive unique databases and their schemas from connector definitions.

    Each connector's target_db and source_dbs become databases.
    Schemas within a db are collected from target_schemas where not "*".
    target_schemas: ["*"] means the connector manages all schemas dynamically.

    Returns:
        {
            "RAW_FIVETRAN": {"schemas": [], "comment": "..."},
            "ANALYTICS":    {"schemas": [],  ...},
            ...
        }
    """
    databases: dict[str, dict] = {}

    def _add_db(name: str, schemas: list[str], reason: str):
        if name not in databases:
            databases[name] = {"schemas": [], "comment": reason}
        for schema in schemas:
            if schema != "*" and schema not in databases[name]["schemas"]:
                databases[name]["schemas"].append(schema)

    for c in connectors:
        # Target database
        target_db = c.get("target_db")
        if target_db:
            schemas = [s for s in c.get("target_schemas", []) if s != "*"]
            _add_db(target_db, schemas, c.get("reason", ""))

        # Source databases (transformer reads from multiple raw dbs)
        for src_db in c.get("source_dbs", []):
            _add_db(src_db, [], f"Source for {c['name']}")

        # bi_tool source_db (read-only access)
        source_db = c.get("source_db")
        if source_db:
            _add_db(source_db, [], f"Read-only source for CONN_{c['name']}")

    return databases


def derive_warehouses(connectors: list[dict]) -> dict:
    """Derive unique warehouses from connector definitions.

    Warehouses are deduplicated by name. If size/budget info is embedded in
    connectors.yaml, it's preserved; otherwise defaults are used.

    Returns:
        {
            "INGEST":    {"size": "XSMALL", "auto_suspend_seconds": 300, ...},
            "TRANSFORM": {...},
            ...
        }
    """
    warehouses: dict[str, dict] = {}
    seen: set[str] = set()

    for c in connectors:
        wh = c.get("warehouse", "").upper()
        if not wh or wh in seen:
            continue
        seen.add(wh)
        warehouses[wh] = {
            "size": c.get("warehouse_size", "XSMALL"),
            "auto_suspend_seconds": c.get("warehouse_auto_suspend_seconds", 300),
            "auto_resume": True,
            "monthly_credit_quota": c.get("warehouse_monthly_credit_quota", 100),
            "notify_at_percentage": c.get("warehouse_notify_at_percentage", 75),
            "suspend_at_percentage": c.get("warehouse_suspend_at_percentage", 100),
            "comment": f"Managed by terraform — derives from connectors.yaml",
        }

    return warehouses


def derive_rbac(connectors: list[dict]) -> dict:
    """Derive the full RBAC structure from connectors.

    Returns a dict with:
        connector_roles:  {name -> {name, reason, type, warehouse}}
        object_roles:     {name -> {privileges, databases, comment}}
        connector_to_object_role_grants:  [{connector, object_role}]
        connector_to_warehouse_grants:    [{connector, warehouse}]
        connector_type_mapping:           {connector -> functional_type}
    """
    connector_roles: dict[str, dict] = {}
    object_roles: dict[str, dict] = {}
    connector_to_obj: list[dict] = []
    connector_to_wh: list[dict] = []
    type_mapping: dict[str, str] = {}

    for c in connectors:
        name = c["name"]
        conn_role = f"CONN_{name}"

        # Connector role
        connector_roles[conn_role] = {
            "name": conn_role,
            "reason": c.get("reason", ""),
            "type": c.get("type", "custom"),
            "warehouse": f"WH_{c['warehouse']}",
        }

        # Functional type mapping
        type_mapping[conn_role] = c.get("type", "custom")

        # Warehouse grant
        connector_to_wh.append({
            "connector_role": conn_role,
            "warehouse": f"WH_{c['warehouse']}",
        })

        # Object role(s)
        target_db = c.get("target_db")
        source_db = c.get("source_db")  # bi_tool pattern
        source_dbs = c.get("source_dbs", [])  # transformer pattern

        if target_db:
            # Determine if this is a writer or reader
            is_writer = any(p in c.get("privileges", []) for p in ["INSERT", "CREATE TABLE", "CREATE SCHEMA"])
            tier = "WRITER" if is_writer else "READER"
            obj_role_name = f"OBJ_{target_db}_{tier}"

            if obj_role_name not in object_roles:
                object_roles[obj_role_name] = {
                    "database": target_db,
                    "tier": tier,
                    "privileges": [],
                    "extra_grants": [],
                    "schemas": [],
                    "comment": f"Object role for {target_db} — {tier.lower()} access",
                }

            # Merge privileges (deduplicate)
            for priv in c.get("privileges", []):
                if priv not in object_roles[obj_role_name]["privileges"]:
                    object_roles[obj_role_name]["privileges"].append(priv)

            for priv in c.get("extra_grants", []):
                if priv not in object_roles[obj_role_name]["extra_grants"]:
                    object_roles[obj_role_name]["extra_grants"].append(priv)

            # Collect non-wildcard schemas
            for schema in c.get("target_schemas", []):
                if schema != "*" and schema not in object_roles[obj_role_name]["schemas"]:
                    object_roles[obj_role_name]["schemas"].append(schema)

            connector_to_obj.append({
                "connector_role": conn_role,
                "object_role": obj_role_name,
            })

        # Reader roles for source databases (transformer)
        for src_db in source_dbs:
            reader_role = f"OBJ_{src_db}_READER"
            if reader_role not in object_roles:
                object_roles[reader_role] = {
                    "database": src_db,
                    "tier": "READER",
                    "privileges": ["SELECT", "USAGE"],
                    "extra_grants": [],
                    "schemas": [],
                    "comment": f"Read-only access to {src_db} for transformer roles",
                }
            connector_to_obj.append({
                "connector_role": conn_role,
                "object_role": reader_role,
            })

        # Reader role for bi_tool source_db
        if source_db:
            reader_role = f"OBJ_{source_db}_READER"
            if reader_role not in object_roles:
                object_roles[reader_role] = {
                    "database": source_db,
                    "tier": "READER",
                    "privileges": ["SELECT", "USAGE"],
                    "extra_grants": [],
                    "schemas": [],
                    "comment": f"Read-only access to {source_db} for BI tools",
                }
            connector_to_obj.append({
                "connector_role": conn_role,
                "object_role": reader_role,
            })

    # Deduplicate connector_to_obj
    seen_pairs: set[tuple] = set()
    deduped_obj = []
    for item in connector_to_obj:
        key = (item["connector_role"], item["object_role"])
        if key not in seen_pairs:
            seen_pairs.add(key)
            deduped_obj.append(item)

    return {
        "connector_roles": connector_roles,
        "object_roles": object_roles,
        "connector_to_object_role_grants": deduped_obj,
        "connector_to_warehouse_grants": connector_to_wh,
        "connector_type_mapping": type_mapping,
    }


def write_tfvars(output_dir: str, databases: dict, warehouses: dict, rbac: dict):
    """Write .auto.tfvars.json files to output_dir."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    db_file = out / "databases.auto.tfvars.json"
    wh_file = out / "warehouses.auto.tfvars.json"
    rbac_file = out / "rbac.auto.tfvars.json"

    db_file.write_text(json.dumps({"databases": databases}, indent=2) + "\n")
    wh_file.write_text(json.dumps({"warehouses": warehouses}, indent=2) + "\n")
    rbac_file.write_text(json.dumps(rbac, indent=2) + "\n")

    return db_file, wh_file, rbac_file


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--connectors",
    default="intake/connectors.yaml",
    show_default=True,
    help="Path to connectors.yaml",
)
@click.option(
    "--tags",
    default="intake/tags.yaml",
    show_default=True,
    help="Path to tags.yaml",
)
@click.option(
    "--output-dir",
    default="terraform",
    show_default=True,
    help="Output directory for .auto.tfvars.json files",
)
@click.option("--dry-run", is_flag=True, help="Print derived config without writing files")
def main(connectors: str, tags: str, output_dir: str, dry_run: bool):
    """Generate Terraform .auto.tfvars.json from intake YAML config.

    Reads connectors.yaml and tags.yaml, derives databases, warehouses, and RBAC
    structure, and writes auto.tfvars.json files consumed by Terraform modules.
    """
    click.echo(f"Loading config from {connectors} + {tags}")
    connector_list, tags_config = load_config(connectors, tags)
    click.echo(f"  {len(connector_list)} connector(s) loaded")

    databases = derive_databases(connector_list)
    warehouses = derive_warehouses(connector_list)
    rbac = derive_rbac(connector_list)

    click.echo(f"\nDerived:")
    click.echo(f"  {len(databases)} database(s): {', '.join(databases.keys())}")
    click.echo(f"  {len(warehouses)} warehouse(s): {', '.join(f'WH_{w}' for w in warehouses.keys())}")
    click.echo(f"  {len(rbac['connector_roles'])} connector role(s)")
    click.echo(f"  {len(rbac['object_roles'])} object role(s)")

    if dry_run:
        click.echo("\n--- DRY RUN --- databases ---")
        click.echo(json.dumps({"databases": databases}, indent=2))
        click.echo("\n--- DRY RUN --- warehouses ---")
        click.echo(json.dumps({"warehouses": warehouses}, indent=2))
        click.echo("\n--- DRY RUN --- rbac ---")
        click.echo(json.dumps(rbac, indent=2))
        return

    db_file, wh_file, rbac_file = write_tfvars(output_dir, databases, warehouses, rbac)

    click.echo(f"\nWritten:")
    click.echo(f"  {db_file}")
    click.echo(f"  {wh_file}")
    click.echo(f"  {rbac_file}")
    click.echo("\nNext: cd terraform && terraform init && terraform plan")


if __name__ == "__main__":
    main()

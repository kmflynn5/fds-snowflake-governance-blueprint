"""
tests/unit/test_generate_tf.py — Unit tests for scripts/generate_tf.py derivation logic
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json

from scripts.generate_tf import (
    derive_databases,
    derive_warehouses,
    derive_rbac,
    derive_functional_roles,
    derive_firefighter_config,
    load_emergency_config,
    write_tfvars,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

EXAMPLE_CONNECTORS = [
    {
        "name": "FIVETRAN",
        "type": "etl",
        "target_db": "RAW_FIVETRAN",
        "target_schemas": ["*"],
        "privileges": ["INSERT", "CREATE TABLE"],
        "warehouse": "INGEST",
        "reason": "Fivetran ETL",
        "vendor_managed": True,
    },
    {
        "name": "AIRFLOW",
        "type": "orchestrator",
        "target_db": "RAW_AIRFLOW",
        "target_schemas": ["*"],
        "privileges": ["INSERT", "CREATE TABLE", "SELECT"],
        "warehouse": "INGEST",
        "reason": "Airflow pipelines",
        "vendor_managed": False,
    },
    {
        "name": "SNOWPIPE_SNOWPLOW",
        "type": "event_stream",
        "target_db": "EVENTS",
        "target_schemas": ["SNOWPLOW"],
        "privileges": ["INSERT"],
        "extra_grants": ["CREATE PIPE", "MONITOR"],
        "warehouse": "INGEST",
        "reason": "Snowpipe from S3",
        "vendor_managed": False,
    },
    {
        "name": "DBT_PROD",
        "type": "transformer",
        "source_dbs": ["RAW_FIVETRAN", "RAW_AIRFLOW", "EVENTS"],
        "target_db": "ANALYTICS",
        "target_schemas": ["*"],
        "privileges": ["SELECT", "INSERT", "CREATE TABLE", "CREATE SCHEMA"],
        "warehouse": "TRANSFORM",
        "reason": "dbt production",
        "vendor_managed": False,
    },
    {
        "name": "LOOKER",
        "type": "bi_tool",
        "source_db": "MARTS",
        "target_schemas": ["*"],
        "privileges": ["SELECT"],
        "warehouse": "ANALYTICS",
        "reason": "Looker BI",
        "vendor_managed": True,
    },
]


# ---------------------------------------------------------------------------
# derive_databases tests
# ---------------------------------------------------------------------------

class TestDeriveDatabases:
    def test_all_target_dbs_created(self):
        databases = derive_databases(EXAMPLE_CONNECTORS)
        assert "RAW_FIVETRAN" in databases
        assert "RAW_AIRFLOW" in databases
        assert "EVENTS" in databases
        assert "ANALYTICS" in databases

    def test_source_dbs_included(self):
        databases = derive_databases(EXAMPLE_CONNECTORS)
        # DBT_PROD reads from RAW_FIVETRAN, RAW_AIRFLOW, EVENTS
        assert "RAW_FIVETRAN" in databases
        assert "RAW_AIRFLOW" in databases
        assert "EVENTS" in databases

    def test_bi_tool_source_db_included(self):
        databases = derive_databases(EXAMPLE_CONNECTORS)
        assert "MARTS" in databases

    def test_wildcard_schemas_not_created(self):
        databases = derive_databases(EXAMPLE_CONNECTORS)
        # FIVETRAN uses target_schemas: ["*"] — no schemas should be listed
        assert databases["RAW_FIVETRAN"]["schemas"] == []

    def test_specific_schemas_created(self):
        databases = derive_databases(EXAMPLE_CONNECTORS)
        # SNOWPIPE_SNOWPLOW uses target_schemas: ["SNOWPLOW"]
        assert "SNOWPLOW" in databases["EVENTS"]["schemas"]

    def test_database_count(self):
        databases = derive_databases(EXAMPLE_CONNECTORS)
        # RAW_FIVETRAN, RAW_AIRFLOW, EVENTS, ANALYTICS, MARTS
        assert len(databases) == 5

    def test_single_connector(self):
        connectors = [{
            "name": "TEST",
            "type": "etl",
            "target_db": "MY_DB",
            "target_schemas": ["my_schema"],
            "privileges": ["INSERT"],
            "warehouse": "INGEST",
            "reason": "test",
        }]
        databases = derive_databases(connectors)
        assert "MY_DB" in databases
        assert "my_schema" in databases["MY_DB"]["schemas"]


# ---------------------------------------------------------------------------
# derive_warehouses tests
# ---------------------------------------------------------------------------

class TestDeriveWarehouses:
    def test_unique_warehouses(self):
        warehouses = derive_warehouses(EXAMPLE_CONNECTORS)
        # INGEST, TRANSFORM, ANALYTICS — deduplicated
        assert "INGEST" in warehouses
        assert "TRANSFORM" in warehouses
        assert "ANALYTICS" in warehouses

    def test_warehouse_count(self):
        warehouses = derive_warehouses(EXAMPLE_CONNECTORS)
        assert len(warehouses) == 3  # INGEST, TRANSFORM, ANALYTICS

    def test_defaults_set(self):
        warehouses = derive_warehouses(EXAMPLE_CONNECTORS)
        wh = warehouses["INGEST"]
        assert wh["size"] == "XSMALL"
        assert wh["auto_suspend_seconds"] == 300
        assert wh["auto_resume"] is True
        assert wh["monthly_credit_quota"] == 100
        assert wh["notify_at_percentage"] == 75
        assert wh["suspend_at_percentage"] == 100

    def test_no_duplicate_warehouses(self):
        # Both FIVETRAN and AIRFLOW use INGEST — should appear only once
        warehouses = derive_warehouses(EXAMPLE_CONNECTORS)
        assert len([k for k in warehouses if k == "INGEST"]) == 1


# ---------------------------------------------------------------------------
# derive_rbac tests
# ---------------------------------------------------------------------------

class TestDeriveRbac:
    def test_connector_roles_created(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        assert "CONN_FIVETRAN" in rbac["connector_roles"]
        assert "CONN_AIRFLOW" in rbac["connector_roles"]
        assert "CONN_DBT_PROD" in rbac["connector_roles"]
        assert "CONN_LOOKER" in rbac["connector_roles"]

    def test_connector_role_count(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        assert len(rbac["connector_roles"]) == 5

    def test_writer_object_roles_created(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        # FIVETRAN → RAW_FIVETRAN has INSERT/CREATE TABLE → WRITER
        assert "OBJ_RAW_FIVETRAN_WRITER" in rbac["object_roles"]
        assert "OBJ_ANALYTICS_WRITER" in rbac["object_roles"]

    def test_reader_object_roles_created(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        # DBT_PROD reads RAW_FIVETRAN, RAW_AIRFLOW, EVENTS → READER roles
        assert "OBJ_RAW_FIVETRAN_READER" in rbac["object_roles"]
        assert "OBJ_RAW_AIRFLOW_READER" in rbac["object_roles"]
        assert "OBJ_EVENTS_READER" in rbac["object_roles"]
        # LOOKER reads MARTS
        assert "OBJ_MARTS_READER" in rbac["object_roles"]

    def test_extra_grants_on_snowpipe_role(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        # SNOWPIPE_SNOWPLOW has extra_grants: [CREATE PIPE, MONITOR]
        obj_role = rbac["object_roles"].get("OBJ_EVENTS_WRITER")
        assert obj_role is not None
        assert "CREATE PIPE" in obj_role["extra_grants"]
        assert "MONITOR" in obj_role["extra_grants"]

    def test_connector_to_object_grants_populated(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        grants = rbac["connector_to_object_role_grants"]
        assert len(grants) > 0
        # CONN_FIVETRAN should be mapped to OBJ_RAW_FIVETRAN_WRITER
        fivetran_grants = [g for g in grants if g["connector_role"] == "CONN_FIVETRAN"]
        assert any(g["object_role"] == "OBJ_RAW_FIVETRAN_WRITER" for g in fivetran_grants)

    def test_connector_to_warehouse_grants_populated(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        wh_grants = rbac["connector_to_warehouse_grants"]
        assert len(wh_grants) == 5
        fivetran_wh = next(g for g in wh_grants if g["connector_role"] == "CONN_FIVETRAN")
        assert fivetran_wh["warehouse"] == "WH_INGEST"

    def test_no_duplicate_object_grants(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        grants = rbac["connector_to_object_role_grants"]
        pairs = [(g["connector_role"], g["object_role"]) for g in grants]
        assert len(pairs) == len(set(pairs)), "Duplicate connector→object role grants found"

    def test_type_mapping_correct(self):
        rbac = derive_rbac(EXAMPLE_CONNECTORS)
        mapping = rbac["connector_type_mapping"]
        assert mapping["CONN_FIVETRAN"] == "etl"
        assert mapping["CONN_DBT_PROD"] == "transformer"
        assert mapping["CONN_LOOKER"] == "bi_tool"

    def test_privilege_merging(self):
        # Two connectors targeting the same db should merge privileges in the object role
        connectors = [
            {
                "name": "TOOL_A",
                "type": "etl",
                "target_db": "SHARED_DB",
                "target_schemas": ["*"],
                "privileges": ["INSERT"],
                "warehouse": "INGEST",
                "reason": "Tool A",
            },
            {
                "name": "TOOL_B",
                "type": "orchestrator",
                "target_db": "SHARED_DB",
                "target_schemas": ["*"],
                "privileges": ["CREATE TABLE"],
                "warehouse": "INGEST",
                "reason": "Tool B",
            },
        ]
        rbac = derive_rbac(connectors)
        obj_role = rbac["object_roles"]["OBJ_SHARED_DB_WRITER"]
        assert "INSERT" in obj_role["privileges"]
        assert "CREATE TABLE" in obj_role["privileges"]


# ---------------------------------------------------------------------------
# derive_functional_roles tests
# ---------------------------------------------------------------------------

EXAMPLE_FUNCTIONAL_ROLES = [
    {
        "name": "DATA_ENGINEER",
        "warehouse": "TRANSFORM",
        "database_access": [
            {"db": "ANALYTICS", "schemas": ["*"], "privileges": ["SELECT", "INSERT"]},
        ],
        "reason": "Data engineers",
    },
    {
        "name": "DATA_ANALYST",
        "warehouse": "ANALYTICS",
        "database_access": [
            {"db": "ANALYTICS", "schemas": ["MARTS", "REPORTS"], "privileges": ["SELECT"]},
        ],
        "reason": "Analysts",
    },
]


class TestDeriveFunctionalRoles:
    def test_single_persona_single_db_schema(self):
        roles = [
            {
                "name": "DATA_ANALYST",
                "warehouse": "ANALYTICS",
                "database_access": [
                    {"db": "ANALYTICS", "schemas": ["MARTS"], "privileges": ["SELECT"]},
                ],
                "reason": "Analysts",
            }
        ]
        result = derive_functional_roles(roles)
        grants = result["functional_role_grants"]
        assert len(grants) == 1
        g = grants[0]
        assert g["role"] == "DATA_ANALYST"
        assert g["database"] == "ANALYTICS"
        assert g["schema"] == "MARTS"
        assert g["privilege"] == "SELECT"
        assert g["future"] is True

    def test_multiple_personas(self):
        result = derive_functional_roles(EXAMPLE_FUNCTIONAL_ROLES)
        role_names = [r["name"] for r in result["functional_roles"]]
        assert "DATA_ENGINEER" in role_names
        assert "DATA_ANALYST" in role_names
        # Warehouse is prefixed with WH_
        engineer = next(r for r in result["functional_roles"] if r["name"] == "DATA_ENGINEER")
        analyst = next(r for r in result["functional_roles"] if r["name"] == "DATA_ANALYST")
        assert engineer["warehouse"] == "WH_TRANSFORM"
        assert analyst["warehouse"] == "WH_ANALYTICS"

    def test_schema_wildcard_expansion(self):
        result = derive_functional_roles(EXAMPLE_FUNCTIONAL_ROLES)
        grants = result["functional_role_grants"]
        # DATA_ENGINEER: schemas: ["*"] → schema == None
        engineer_grants = [g for g in grants if g["role"] == "DATA_ENGINEER"]
        assert all(g["schema"] is None for g in engineer_grants)
        # DATA_ANALYST: named schemas → schema in ["MARTS", "REPORTS"]
        analyst_grants = [g for g in grants if g["role"] == "DATA_ANALYST"]
        analyst_schemas = {g["schema"] for g in analyst_grants}
        assert "MARTS" in analyst_schemas
        assert "REPORTS" in analyst_schemas

    def test_multi_privilege_expansion(self):
        result = derive_functional_roles(EXAMPLE_FUNCTIONAL_ROLES)
        grants = result["functional_role_grants"]
        # DATA_ENGINEER has [SELECT, INSERT] on one db — should produce two grant entries
        engineer_grants = [g for g in grants if g["role"] == "DATA_ENGINEER"]
        privileges = {g["privilege"] for g in engineer_grants}
        assert "SELECT" in privileges
        assert "INSERT" in privileges
        # Two separate entries (one per privilege)
        assert len(engineer_grants) == 2


# ---------------------------------------------------------------------------
# derive_firefighter_config tests
# ---------------------------------------------------------------------------

EXAMPLE_EMERGENCY = {
    "authorized_contacts": [
        {"name": "Alice", "title": "Lead DE", "contact": "@alice"},
        {"name": "Bob", "title": "Platform Eng", "contact": "@bob"},
    ],
    "notification_process": "#incidents",
    "deactivation_sla": "within_24h",
}


class TestDeriveFirefighterConfig:
    def test_contacts_preserved(self):
        result = derive_firefighter_config(EXAMPLE_EMERGENCY)
        assert result["authorized_contacts"] == EXAMPLE_EMERGENCY["authorized_contacts"]

    def test_notification_process_preserved(self):
        result = derive_firefighter_config(EXAMPLE_EMERGENCY)
        assert result["notification_process"] == "#incidents"

    def test_sla_preserved(self):
        result = derive_firefighter_config(EXAMPLE_EMERGENCY)
        assert result["deactivation_sla"] == "within_24h"

    def test_empty_dict_returns_safe_defaults(self):
        result = derive_firefighter_config({})
        assert result["authorized_contacts"] == []
        assert result["notification_process"] == ""
        assert result["deactivation_sla"] == "within_24h"

    def test_output_keys(self):
        result = derive_firefighter_config(EXAMPLE_EMERGENCY)
        assert set(result.keys()) == {"authorized_contacts", "notification_process", "deactivation_sla"}


# ---------------------------------------------------------------------------
# load_emergency_config tests
# ---------------------------------------------------------------------------

class TestLoadEmergencyConfig:
    def test_returns_none_when_file_missing(self, tmp_path):
        result = load_emergency_config(str(tmp_path / "team.yaml"))
        assert result is None

    def test_returns_none_when_key_absent(self, tmp_path):
        team_file = tmp_path / "team.yaml"
        team_file.write_text("functional_roles: []\n")
        result = load_emergency_config(str(team_file))
        assert result is None

    def test_returns_emergency_config(self, tmp_path):
        import yaml
        team_file = tmp_path / "team.yaml"
        team_file.write_text(yaml.dump({
            "functional_roles": [],
            "emergency_access": EXAMPLE_EMERGENCY,
        }))
        result = load_emergency_config(str(team_file))
        assert result is not None
        assert result["notification_process"] == "#incidents"
        assert len(result["authorized_contacts"]) == 2


# ---------------------------------------------------------------------------
# write_tfvars — firefighter_config inclusion tests
# ---------------------------------------------------------------------------

class TestWriteTfvarsFirefighter:
    def _minimal_inputs(self):
        return {}, {}, {
            "connector_roles": {},
            "object_roles": {},
            "connector_to_object_role_grants": [],
            "connector_to_warehouse_grants": [],
            "connector_type_mapping": {},
        }, {"functional_roles": [], "functional_role_grants": []}

    def test_firefighter_config_written_to_rbac(self, tmp_path):
        databases, warehouses, rbac, functional = self._minimal_inputs()
        ff = derive_firefighter_config(EXAMPLE_EMERGENCY)
        _, _, rbac_file = write_tfvars(str(tmp_path), databases, warehouses, rbac, functional, ff)
        payload = json.loads(rbac_file.read_text())
        assert "firefighter_config" in payload
        assert payload["firefighter_config"]["notification_process"] == "#incidents"
        assert len(payload["firefighter_config"]["authorized_contacts"]) == 2

    def test_firefighter_config_absent_when_none(self, tmp_path):
        databases, warehouses, rbac, functional = self._minimal_inputs()
        _, _, rbac_file = write_tfvars(str(tmp_path), databases, warehouses, rbac, functional, None)
        payload = json.loads(rbac_file.read_text())
        assert "firefighter_config" not in payload

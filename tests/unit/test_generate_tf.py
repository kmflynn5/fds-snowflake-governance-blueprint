"""
tests/unit/test_generate_tf.py — Unit tests for scripts/generate_tf.py derivation logic
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from scripts.generate_tf import derive_databases, derive_warehouses, derive_rbac


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

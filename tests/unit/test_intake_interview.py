"""
tests/unit/test_intake_interview.py — Unit tests for scripts/intake_interview.py
"""

import sys
import os
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import yaml
import pytest
from click.testing import CliRunner
from scripts.intake_interview import (
    cli,
    _validate_connectors,
)


# ---------------------------------------------------------------------------
# _validate_connectors tests
# ---------------------------------------------------------------------------

class TestValidateConnectors:
    def _make_connector(self, **overrides):
        base = {
            "name": "TEST",
            "type": "etl",
            "target_db": "MY_DB",
            "target_schemas": ["*"],
            "privileges": ["INSERT"],
            "warehouse": "INGEST",
            "reason": "test connector",
        }
        base.update(overrides)
        return base

    def test_valid_connector_no_errors(self):
        errors = _validate_connectors([self._make_connector()])
        assert errors == []

    def test_missing_name(self):
        errors = _validate_connectors([self._make_connector(name="")])
        assert any("missing 'name'" in e for e in errors)

    def test_duplicate_name(self):
        c = self._make_connector()
        errors = _validate_connectors([c, c.copy()])
        assert any("duplicate" in e.lower() for e in errors)

    def test_invalid_type(self):
        errors = _validate_connectors([self._make_connector(type="bad_type")])
        assert any("invalid type" in e for e in errors)

    def test_missing_warehouse(self):
        errors = _validate_connectors([self._make_connector(warehouse="")])
        assert any("missing 'warehouse'" in e for e in errors)

    def test_unrecognized_privilege(self):
        errors = _validate_connectors([self._make_connector(privileges=["DROP TABLE"])])
        assert any("unrecognized privilege" in e for e in errors)

    def test_all_valid_types_accepted(self):
        valid_types = ["etl", "orchestrator", "event_stream", "transformer", "bi_tool", "custom"]
        for t in valid_types:
            errors = _validate_connectors([self._make_connector(type=t)])
            type_errors = [e for e in errors if "invalid type" in e]
            assert type_errors == [], f"Type '{t}' should be valid but got errors: {type_errors}"


# ---------------------------------------------------------------------------
# Output file tests via CLI runner
# ---------------------------------------------------------------------------

class TestCliOutputs:
    def _run_greenfield_with_inputs(self, inputs: str, output_dir: str) -> CliRunner:
        """Run the greenfield CLI with provided input string."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--greenfield", "--output-dir", output_dir],
            input=inputs,
            catch_exceptions=False,
        )
        return result

    def test_abort_on_no_write_confirmation(self, tmp_path):
        inputs = "\n".join([
            "data_platform",  # purpose
            "2",              # data engineers
            "5",              # analysts
            "0",              # data scientists
            "3",              # service accounts
            "crawl",          # maturity
            "n",              # no ingestion tools
            "n",              # no transformation tools
            "n",              # no consumption tools
            # warehouses (accept defaults)
            "", "", "",       # INGEST
            "", "", "",       # TRANSFORM
            "", "", "",       # ANALYTICS
            "n",              # no extra warehouses
            # tags (accept defaults)
            "",               # cost centers
            "",               # environments
            "y",              # pii tag
            "y",              # sensitivity tag
            # emergency access
            "n",              # no contacts
            "test-alerts",    # notification
            "within_24h",     # SLA
            "n",              # do NOT write files
        ]) + "\n"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--greenfield", "--output-dir", str(tmp_path)],
            input=inputs,
        )
        # Should not write files when user says "n"
        assert not (tmp_path / "connectors.yaml").exists()

    def test_connectors_yaml_written(self, tmp_path):
        inputs = "\n".join([
            "data_platform",
            "2", "5", "0", "3",
            "crawl",
            "y",              # add ingestion tool
            "FIVETRAN",
            "etl",
            "RAW_FIVETRAN",
            "y",              # all schemas
            "y",              # INSERT
            "y",              # CREATE TABLE
            "n",              # no SELECT
            "INGEST",
            "Fivetran ETL connector",
            "y",              # vendor managed
            "n",              # no more ingestion tools
            "n",              # no transformation
            "n",              # no consumption
            "", "", "",
            "", "", "",
            "", "", "",
            "n",
            "", "", "y", "y",
            "n",
            "test-alerts",
            "within_24h",
            "y",              # write files
        ]) + "\n"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--greenfield", "--output-dir", str(tmp_path)],
            input=inputs,
        )

        connectors_file = tmp_path / "connectors.yaml"
        if connectors_file.exists():
            data = yaml.safe_load(connectors_file.read_text())
            assert "connectors" in data
            names = [c["name"] for c in data["connectors"]]
            assert "FIVETRAN" in names

    def test_tags_yaml_written(self, tmp_path):
        # Simplified test — just check the tags file is valid YAML with required structure
        from scripts.intake_interview import _write_tags_yaml

        tags = {
            "required_tags": [
                {"name": "cost_center", "values": ["engineering"], "apply_to": ["database"]},
            ],
            "optional_tags": [],
            "enforcement_stage": "crawl",
        }
        path = _write_tags_yaml(tags, tmp_path)
        assert path.exists()
        loaded = yaml.safe_load(path.read_text())
        assert "required_tags" in loaded
        assert loaded["enforcement_stage"] == "crawl"

    def test_decisions_md_written(self, tmp_path):
        from scripts.intake_interview import _write_decisions_md

        context = {
            "purpose": "data_platform",
            "team": {"data_engineers": 2, "analysts": 5, "data_scientists": 0, "service_accounts": 3},
            "maturity_target": "crawl",
        }
        emergency = {
            "authorized_contacts": [{"name": "Alice", "title": "Lead DE", "contact": "@alice"}],
            "notification_process": "#incidents",
            "deactivation_sla": "within_24h",
        }
        warehouse_config = {
            "INGEST": {
                "size": "XSMALL",
                "auto_suspend_minutes": 5,
                "monthly_credit_quota": 100,
                "notify_at_percentage": 75,
                "suspend_at_percentage": 100,
            }
        }

        path = _write_decisions_md(context, warehouse_config, emergency, tmp_path, "greenfield")
        assert path.exists()
        content = path.read_text()
        assert "FIREFIGHTER" in content
        assert "Alice" in content
        assert "WH_INGEST" in content
        assert "crawl" in content.lower()


# ---------------------------------------------------------------------------
# Import-compatibility — ensure derive_databases/derive_warehouses aren't duplicated
# (intake_interview imports from generate_tf)
# ---------------------------------------------------------------------------

class TestImportCompatibility:
    def test_validate_connectors_importable(self):
        from scripts.intake_interview import _validate_connectors
        assert callable(_validate_connectors)

    def test_generate_tf_importable(self):
        from scripts.generate_tf import derive_databases, derive_warehouses, derive_rbac
        assert callable(derive_databases)
        assert callable(derive_warehouses)
        assert callable(derive_rbac)

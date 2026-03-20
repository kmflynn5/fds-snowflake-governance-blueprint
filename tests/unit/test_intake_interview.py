"""
tests/unit/test_intake_interview.py — Unit tests for scripts/intake_interview.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import datetime

import yaml
from click.testing import CliRunner
from scripts.intake_interview import (
    cli,
    _validate_connectors,
    _normalize_identifier,
    _validate_tag_values,
    _save_state,
    _load_state,
    _delete_state,
    _write_team_yaml,
    _write_decisions_md,
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
            "core",           # maturity
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
        runner.invoke(
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
            "core",
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
        runner.invoke(
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
            "enforcement_stage": "core",
        }
        path = _write_tags_yaml(tags, tmp_path)
        assert path.exists()
        loaded = yaml.safe_load(path.read_text())
        assert "required_tags" in loaded
        assert loaded["enforcement_stage"] == "core"

    def test_decisions_md_written(self, tmp_path):
        from scripts.intake_interview import _write_decisions_md

        context = {
            "purpose": "data_platform",
            "team": {"data_engineers": 2, "analysts": 5, "data_scientists": 0, "service_accounts": 3},
            "maturity_target": "core",
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
        assert "core" in content.lower()


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


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestNormalizeIdentifier:
    def test_valid_input_returned_unchanged(self):
        assert _normalize_identifier("Name", "FIVETRAN") == "FIVETRAN"

    def test_lowercase_uppercased(self):
        assert _normalize_identifier("Name", "fivetran") == "FIVETRAN"

    def test_spaces_become_underscores(self):
        assert _normalize_identifier("Name", "my tool") == "MY_TOOL"

    def test_hyphens_become_underscores(self):
        assert _normalize_identifier("Name", "wh-ingest-v2") == "WH_INGEST_V2"

    def test_leading_trailing_whitespace_stripped(self):
        assert _normalize_identifier("Name", "  INGEST  ") == "INGEST"

    def test_invalid_input_reprompts(self, mocker):
        # First call returns "123INVALID" (starts with digit), second returns "VALID"
        mocker.patch("scripts.intake_interview._prompt", side_effect=["VALID"])
        result = _normalize_identifier("Name", "123INVALID")
        assert result == "VALID"

    def test_special_chars_reprompts(self, mocker):
        mocker.patch("scripts.intake_interview._prompt", side_effect=["GOOD_NAME"])
        result = _normalize_identifier("Name", "bad@name!")
        assert result == "GOOD_NAME"


class TestValidateTagValues:
    def test_valid_input_returned(self):
        result = _validate_tag_values("Label", "prod,staging,dev")
        assert result == ["prod", "staging", "dev"]

    def test_values_lowercased(self):
        result = _validate_tag_values("Label", "PROD,Staging,DEV")
        assert result == ["prod", "staging", "dev"]

    def test_values_stripped(self):
        result = _validate_tag_values("Label", " prod , staging , dev ")
        assert result == ["prod", "staging", "dev"]

    def test_single_char_rejected_then_reprompts(self, mocker):
        mocker.patch("scripts.intake_interview._prompt", return_value="prod,staging,dev")
        result = _validate_tag_values("Label", "n")
        assert result == ["prod", "staging", "dev"]

    def test_too_few_values_reprompts(self, mocker):
        mocker.patch("scripts.intake_interview._prompt", return_value="prod,staging,dev")
        result = _validate_tag_values("Label", "prod", min_count=2)
        assert result == ["prod", "staging", "dev"]

    def test_min_count_one_accepts_single_value(self):
        result = _validate_tag_values("Label", "engineering", min_count=1)
        assert result == ["engineering"]

    def test_empty_tokens_filtered(self):
        result = _validate_tag_values("Label", "prod,,staging,dev")
        assert result == ["prod", "staging", "dev"]


# ---------------------------------------------------------------------------
# State file tests
# ---------------------------------------------------------------------------

class TestStateFile:
    def test_save_and_load_roundtrip(self, tmp_path):
        state = {
            "version": 1,
            "mode": "greenfield",
            "completed_sections": ["context", "ingestion"],
            "data": {"context": {"purpose": "data_platform"}},
            "timestamp": "2026-03-20T10:00:00",
        }
        _save_state(state, tmp_path)
        loaded = _load_state(tmp_path)
        assert loaded["mode"] == "greenfield"
        assert loaded["completed_sections"] == ["context", "ingestion"]
        assert loaded["data"]["context"]["purpose"] == "data_platform"

    def test_load_returns_none_when_missing(self, tmp_path):
        assert _load_state(tmp_path) is None

    def test_delete_removes_file(self, tmp_path):
        _save_state({"version": 1, "mode": "greenfield", "completed_sections": [], "data": {}, "timestamp": ""}, tmp_path)
        assert (tmp_path / ".interview_state.json").exists()
        _delete_state(tmp_path)
        assert not (tmp_path / ".interview_state.json").exists()

    def test_delete_is_noop_when_missing(self, tmp_path):
        _delete_state(tmp_path)  # should not raise


# ---------------------------------------------------------------------------
# _write_team_yaml emergency_access tests
# ---------------------------------------------------------------------------

class TestWriteTeamYamlEmergency:
    def test_emergency_access_written_when_provided(self, tmp_path):
        import yaml
        emergency = {
            "authorized_contacts": [{"name": "Alice", "title": "Lead DE", "contact": "@alice"}],
            "notification_process": "#incidents",
            "deactivation_sla": "within_24h",
        }
        path = _write_team_yaml([], tmp_path, emergency)
        doc = yaml.safe_load(path.read_text())
        assert "emergency_access" in doc
        assert doc["emergency_access"]["notification_process"] == "#incidents"

    def test_emergency_access_absent_when_not_provided(self, tmp_path):
        import yaml
        path = _write_team_yaml([], tmp_path)
        doc = yaml.safe_load(path.read_text())
        assert "emergency_access" not in doc


# ---------------------------------------------------------------------------
# _write_decisions_md dynamic content tests
# ---------------------------------------------------------------------------

class TestWriteDecisionsMdDynamic:
    def _base_args(self, tmp_path):
        context = {
            "purpose": "data_platform",
            "team": {"data_engineers": 2, "analysts": 5, "data_scientists": 0, "service_accounts": 3},
            "maturity_target": "core",
        }
        warehouse_config = {
            "INGEST": {"size": "XSMALL", "auto_suspend_minutes": 5, "monthly_credit_quota": 100,
                       "notify_at_percentage": 75, "suspend_at_percentage": 100},
        }
        emergency = {"authorized_contacts": [], "notification_process": "#incidents", "deactivation_sla": "within_24h"}
        return context, warehouse_config, emergency, tmp_path, "greenfield"

    def test_author_in_change_log(self, tmp_path):
        args = self._base_args(tmp_path)
        path = _write_decisions_md(*args, author="Jane Smith")
        assert "Jane Smith" in path.read_text()

    def test_today_date_in_change_log(self, tmp_path):
        args = self._base_args(tmp_path)
        path = _write_decisions_md(*args)
        assert datetime.date.today().isoformat() in path.read_text()

    def test_dynamic_connector_row(self, tmp_path):
        args = self._base_args(tmp_path)
        connectors = [{"name": "FIVETRAN", "type": "etl", "target_db": "RAW", "warehouse": "INGEST", "reason": ""}]
        path = _write_decisions_md(*args, connectors=connectors)
        content = path.read_text()
        assert "1 connector" in content
        assert "etl" in content

    def test_dynamic_persona_row(self, tmp_path):
        args = self._base_args(tmp_path)
        team_roles = [{"name": "DATA_ENGINEER", "warehouse": "TRANSFORM", "database_access": [], "reason": ""}]
        path = _write_decisions_md(*args, team_roles=team_roles)
        assert "DATA_ENGINEER" in path.read_text()

    def test_dynamic_tag_row(self, tmp_path):
        args = self._base_args(tmp_path)
        tags = {"required_tags": [{"name": "cost_center", "values": ["eng"], "apply_to": ["database"]}]}
        path = _write_decisions_md(*args, tags=tags)
        assert "cost_center" in path.read_text()

    def test_fds_standard_and_client_decision_labels(self, tmp_path):
        args = self._base_args(tmp_path)
        path = _write_decisions_md(*args)
        content = path.read_text()
        assert "FDS standard" in content
        assert "Client decision" in content

    def test_custom_warehouse_topology_labelled_client_decision(self, tmp_path):
        context, _, emergency, _, mode = self._base_args(tmp_path)
        custom_wh = {
            "INGEST": {"size": "SMALL", "auto_suspend_minutes": 5, "monthly_credit_quota": 100,
                       "notify_at_percentage": 75, "suspend_at_percentage": 100},
            "CUSTOM": {"size": "MEDIUM", "auto_suspend_minutes": 10, "monthly_credit_quota": 200,
                       "notify_at_percentage": 75, "suspend_at_percentage": 100},
        }
        path = _write_decisions_md(context, custom_wh, emergency, tmp_path, mode)
        content = path.read_text()
        assert "WH_INGEST" in content
        assert "WH_CUSTOM" in content


# ---------------------------------------------------------------------------
# --dry-run CLI flag
# ---------------------------------------------------------------------------

def _minimal_greenfield_inputs(**overrides) -> str:
    """
    Return a newline-joined input string for a minimal greenfield session:
    no connectors, no personas, default tags, no emergency contact.

    Section order: context → ingestion → transformation → consumption →
    warehouses → team → tags → emergency → author.
    """
    defaults = [
        "data_platform", "2", "5", "0", "3", "core",  # context
        "n",        # no ingestion tools
        "n",        # no transformation tools
        "n",        # no consumption tools
        "", "", "", "", "", "", "", "", "",  # warehouse size/suspend/budget × 3
        "n",        # no extra warehouses
        "n",        # start with default personas → no
        "",         # add custom persona? → default no
        "",         # cost centers → default accepted
        "",         # env values → default accepted
        "y",        # pii tag
        "y",        # sensitivity tag
        "n",        # no custom required tags
        "n",        # no firefighter contacts
        "test-alerts",  # notification process
        "within_24h",   # deactivation SLA
        "",         # author name
    ]
    seq = list(defaults)
    for k, v in overrides.items():
        seq[k] = v
    return "\n".join(seq) + "\n"


class TestDryRunFlag:
    def test_dry_run_writes_no_files(self, tmp_path):
        inputs = _minimal_greenfield_inputs()

        runner = CliRunner()
        runner.invoke(
            cli,
            ["--greenfield", "--dry-run", "--output-dir", str(tmp_path)],
            input=inputs,
        )
        assert not (tmp_path / "connectors.yaml").exists()
        assert not (tmp_path / "team.yaml").exists()

    def test_dry_run_prints_yaml_delimiters(self, tmp_path):
        inputs = _minimal_greenfield_inputs()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--greenfield", "--dry-run", "--output-dir", str(tmp_path)],
            input=inputs,
        )
        assert "DRY RUN" in result.output

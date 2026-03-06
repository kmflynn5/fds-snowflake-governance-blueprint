"""
tests/unit/test_audit.py — Unit tests for scripts/audit.py with mocked Snowflake connections
"""

import json
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from click.testing import CliRunner
from scripts.audit import cli, _serialize, _run_query, SURVEYS


# ---------------------------------------------------------------------------
# _serialize tests
# ---------------------------------------------------------------------------

class TestSerialize:
    def test_datetime(self):
        import datetime
        dt = datetime.datetime(2026, 1, 15, 12, 0, 0)
        assert _serialize(dt) == "2026-01-15T12:00:00"

    def test_date(self):
        import datetime
        d = datetime.date(2026, 1, 15)
        assert _serialize(d) == "2026-01-15"

    def test_decimal(self):
        import decimal
        d = decimal.Decimal("12.34")
        assert _serialize(d) == pytest.approx(12.34)

    def test_unknown_type_raises(self):
        with pytest.raises(TypeError):
            _serialize(object())


# ---------------------------------------------------------------------------
# _run_query tests
# ---------------------------------------------------------------------------

class TestRunQuery:
    def test_returns_list_of_dicts(self):
        cursor = MagicMock()
        cursor.description = [("name",), ("value",)]
        cursor.fetchall.return_value = [("foo", 1), ("bar", 2)]

        result = _run_query(cursor, "SELECT name, value FROM t")
        assert result == [{"name": "foo", "value": 1}, {"name": "bar", "value": 2}]

    def test_column_names_lowercased(self):
        cursor = MagicMock()
        cursor.description = [("ROLE_NAME",), ("GRANTED_TO",)]
        cursor.fetchall.return_value = [("SYSADMIN", "USER")]

        result = _run_query(cursor, "SELECT ROLE_NAME, GRANTED_TO FROM t")
        assert "role_name" in result[0]
        assert "granted_to" in result[0]

    def test_empty_result(self):
        cursor = MagicMock()
        cursor.description = [("col",)]
        cursor.fetchall.return_value = []
        result = _run_query(cursor, "SELECT col FROM t")
        assert result == []


# ---------------------------------------------------------------------------
# CLI: keygen command
# ---------------------------------------------------------------------------

class TestKeygen:
    def test_keygen_output(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["keygen"])
        assert result.exit_code == 0, result.output
        assert "Paste this into audit_setup.sql" in result.output
        assert (tmp_path / "audit_key.p8").exists()

    def test_public_key_no_headers(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["keygen"])
        # Public key body should not contain PEM headers
        lines = [l for l in result.output.splitlines() if "-----" in l]
        # Only the err output has PEM header context, stdout body should be clean
        assert "-----BEGIN" not in result.output.split("Paste this")[1]


# ---------------------------------------------------------------------------
# CLI: audit --dry-run command
# ---------------------------------------------------------------------------

class TestAuditDryRun:
    def test_dry_run_prints_queries(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "1_1_role_inventory" in result.output
        assert "SELECT" in result.output

    def test_dry_run_no_connection(self):
        # dry-run should not attempt a Snowflake connection
        runner = CliRunner()
        with patch("scripts.audit._get_connection") as mock_conn:
            result = runner.invoke(cli, ["audit", "--dry-run"])
            mock_conn.assert_not_called()
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# CLI: report command
# ---------------------------------------------------------------------------

class TestReport:
    def _write_survey_fixtures(self, tmp_path: Path):
        survey_dir = tmp_path / "intake" / "survey_output"
        survey_dir.mkdir(parents=True)

        # Critical finding: ACCOUNTADMIN user
        (survey_dir / "1_2_user_inventory.json").write_text(json.dumps({
            "users": [{"name": "ADMIN", "login_name": "admin@example.com", "email": "admin@example.com", "default_role": "ACCOUNTADMIN", "last_success_login": "2026-01-01"}],
            "accountadmin_users": [{"user_name": "ADMIN"}],
        }))
        # Critical finding: direct grants
        (survey_dir / "1_3_direct_grants.json").write_text(json.dumps({
            "direct_grants": [{"grantee_name": "JDOE", "granted_on": "TABLE", "privilege": "SELECT"}],
        }))
        # Critical finding: unmonitored warehouses
        (survey_dir / "1_5_resource_monitor_coverage.json").write_text(json.dumps({
            "unmonitored_warehouses": [{"warehouse_name": "COMPUTE_WH"}],
        }))
        # No tags
        (survey_dir / "1_6_tag_coverage.json").write_text(json.dumps({
            "tag_references": [],
            "databases_schemas": [],
        }))
        # Empty ACCOUNTADMIN activity
        (survey_dir / "1_7_accountadmin_activity.json").write_text(json.dumps({
            "accountadmin_queries": [],
        }))
        return survey_dir

    def test_report_generates_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        survey_dir = self._write_survey_fixtures(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["report", str(survey_dir)])
        assert result.exit_code == 0, result.output
        report = (tmp_path / "intake" / "gap_report.md")
        assert report.exists()

    def test_report_contains_critical_findings(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        survey_dir = self._write_survey_fixtures(tmp_path)
        runner = CliRunner()
        runner.invoke(cli, ["report", str(survey_dir)])
        report_text = (tmp_path / "intake" / "gap_report.md").read_text()
        assert "ACCOUNTADMIN" in report_text
        assert "Direct object grants" in report_text
        assert "Warehouses without resource monitors" in report_text

    def test_report_missing_survey_dir(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["report", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0

    def test_report_summary_stats(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        survey_dir = self._write_survey_fixtures(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["report", str(survey_dir)])
        assert "Critical findings:" in result.output


# ---------------------------------------------------------------------------
# SURVEYS structure validation
# ---------------------------------------------------------------------------

class TestSurveysStructure:
    def test_all_sections_have_queries(self):
        for section, config in SURVEYS.items():
            assert "description" in config, f"{section} missing description"
            assert "queries" in config, f"{section} missing queries"
            assert len(config["queries"]) > 0, f"{section} has no queries"

    def test_all_queries_are_strings(self):
        for section, config in SURVEYS.items():
            for name, sql in config["queries"].items():
                assert isinstance(sql, str), f"{section}.{name} is not a string"
                assert len(sql.strip()) > 0, f"{section}.{name} is empty"

    def test_section_count(self):
        # brownfield_intake.md has 8 sections (1.1–1.8)
        assert len(SURVEYS) == 8

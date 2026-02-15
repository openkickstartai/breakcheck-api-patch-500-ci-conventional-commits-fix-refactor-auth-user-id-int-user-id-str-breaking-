"""Tests for BreakCheck formatters — JSON, SARIF, and Table output."""
import json
import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from formatters import JsonFormatter, SarifFormatter, TableFormatter
from breakcheck import app

runner = CliRunner()

# -- Shared fixture data ------------------------------------------------

SAMPLE_CHANGES = [
    {
        "level": "major",
        "kind": "function_removed",
        "symbol": "api.hello",
        "detail": "function hello was removed",
    },
    {
        "level": "minor",
        "kind": "param_added",
        "symbol": "api.fetch",
        "detail": "added optional param timeout",
    },
    {
        "level": "major",
        "kind": "type_changed",
        "symbol": "api.auth",
        "detail": "user_id: int -> str",
    },
]


# -- JsonFormatter tests ------------------------------------------------

def test_json_formatter_produces_valid_json():
    fmt = JsonFormatter()
    output = fmt.format(SAMPLE_CHANGES)
    parsed = json.loads(output)
    assert isinstance(parsed, list)
    assert len(parsed) == 3


def test_json_formatter_contains_required_fields():
    fmt = JsonFormatter()
    output = fmt.format(SAMPLE_CHANGES)
    parsed = json.loads(output)
    required_keys = {"kind", "target", "old_signature", "new_signature", "severity", "file", "line"}
    for item in parsed:
        assert required_keys.issubset(item.keys()), f"Missing keys in {item.keys()}"


def test_json_formatter_severity_mapping():
    fmt = JsonFormatter()
    output = fmt.format(SAMPLE_CHANGES)
    parsed = json.loads(output)
    assert parsed[0]["severity"] == "major"
    assert parsed[1]["severity"] == "minor"


def test_json_formatter_empty_changes():
    fmt = JsonFormatter()
    output = fmt.format([])
    parsed = json.loads(output)
    assert parsed == []


# -- SarifFormatter tests -----------------------------------------------

def test_sarif_formatter_produces_valid_sarif_structure():
    fmt = SarifFormatter()
    output = fmt.format(SAMPLE_CHANGES)
    parsed = json.loads(output)
    assert parsed["version"] == "2.1.0"
    assert "$schema" in parsed
    assert "runs" in parsed
    assert len(parsed["runs"]) == 1
    run = parsed["runs"][0]
    assert "tool" in run
    assert "results" in run
    assert run["tool"]["driver"]["name"] == "BreakCheck"


def test_sarif_formatter_level_mapping():
    fmt = SarifFormatter()
    output = fmt.format(SAMPLE_CHANGES)
    parsed = json.loads(output)
    results = parsed["runs"][0]["results"]
    levels = [r["level"] for r in results]
    assert "error" in levels  # major -> error
    assert "warning" in levels  # minor -> warning


def test_sarif_formatter_rules_deduplication():
    """Two changes with same kind should produce only one rule entry."""
    dup_changes = [
        {"level": "major", "kind": "function_removed", "symbol": "a.foo", "detail": "removed"},
        {"level": "major", "kind": "function_removed", "symbol": "a.bar", "detail": "removed"},
    ]
    fmt = SarifFormatter()
    parsed = json.loads(fmt.format(dup_changes))
    rules = parsed["runs"][0]["tool"]["driver"]["rules"]
    assert len(rules) == 1
    assert rules[0]["id"] == "function_removed"
    assert len(parsed["runs"][0]["results"]) == 2


def test_sarif_formatter_empty_changes():
    fmt = SarifFormatter()
    output = fmt.format([])
    parsed = json.loads(output)
    assert parsed["version"] == "2.1.0"
    assert parsed["runs"][0]["results"] == []


def test_sarif_locations_have_artifact_and_region():
    fmt = SarifFormatter()
    output = fmt.format(SAMPLE_CHANGES)
    parsed = json.loads(output)
    for result in parsed["runs"][0]["results"]:
        loc = result["locations"][0]["physicalLocation"]
        assert "artifactLocation" in loc
        assert "uri" in loc["artifactLocation"]
        assert "region" in loc
        assert "startLine" in loc["region"]


# -- TableFormatter tests -----------------------------------------------

def test_table_formatter_empty_changes():
    fmt = TableFormatter()
    output = fmt.format([])
    assert "No public API changes detected" in output


def test_table_formatter_contains_symbols():
    fmt = TableFormatter()
    output = fmt.format(SAMPLE_CHANGES)
    assert "api.hello" in output
    assert "api.fetch" in output
    assert "api.auth" in output


# -- CLI integration tests (end-to-end via Typer) -----------------------

def _make(tmpdir, filename, code):
    (Path(tmpdir) / filename).write_text(code)


def test_cli_compare_json_format():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def hello(name: str) -> str:\n    return name\n")
        _make(new, "api.py", "def goodbye() -> None:\n    return None\n")
        result = runner.invoke(app, ["compare", old, new, "--format", "json"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)
        assert len(parsed) > 0
        assert all("severity" in item for item in parsed)


def test_cli_compare_sarif_format():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def hello(name: str) -> str:\n    return name\n")
        _make(new, "api.py", "def hello(name: str, age: int = 0) -> str:\n    return name\n")
        result = runner.invoke(app, ["compare", old, new, "--format", "sarif"])
        assert result.exit_code == 0
        parsed = json.loads(result.stdout)
        assert parsed["version"] == "2.1.0"
        assert len(parsed["runs"][0]["results"]) > 0


def test_cli_compare_default_table_format():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def hello(name: str) -> str:\n    return name\n")
        _make(new, "api.py", "def hello(name: str) -> str:\n    return name\n")
        result = runner.invoke(app, ["compare", old, new])
        assert result.exit_code == 0
        assert "No public API changes detected" in result.stdout

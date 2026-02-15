"""Tests for BreakCheck — 9 test cases covering core detection & gate logic."""
import tempfile
from pathlib import Path
from typer.testing import CliRunner
from breakcheck import app
from analyzer import extract_api, diff_api, max_level

runner = CliRunner()


def _make(tmpdir, filename, code):
    (Path(tmpdir) / filename).write_text(code)


def test_function_removed_is_major():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def hello(name: str) -> str:\n    return name\n")
        _make(new, "api.py", "def goodbye() -> None:\n    return None\n")
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["level"] == "major" and c["kind"] == "function_removed" for c in changes)
        assert max_level(changes) == "major"


def test_param_type_change_is_major():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def auth(user_id: int) -> bool:\n    return True\n")
        _make(new, "api.py", "def auth(user_id: str) -> bool:\n    return True\n")
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["level"] == "major" and c["kind"] == "type_changed" for c in changes)
        assert max_level(changes) == "major"


def test_optional_param_added_is_minor():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", 'def fetch(url: str) -> str:\n    return "ok"\n')
        _make(new, "api.py", 'def fetch(url: str, timeout: int = 30) -> str:\n    return "ok"\n')
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["level"] == "minor" and c["kind"] == "param_added" for c in changes)
        assert max_level(changes) == "minor"


def test_required_param_added_is_major():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", 'def fetch(url: str) -> str:\n    return "ok"\n')
        _make(new, "api.py", 'def fetch(url: str, token: str) -> str:\n    return "ok"\n')
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["level"] == "major" and "REQUIRED" in c["detail"] for c in changes)
        assert max_level(changes) == "major"


def test_no_changes_returns_patch():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        code = 'def fetch(url: str) -> str:\n    return "ok"\n'
        _make(old, "api.py", code)
        _make(new, "api.py", code)
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert changes == []
        assert max_level(changes) == "patch"


def test_gate_blocks_breaking_change():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def hello(name: str) -> str:\n    return name\n")
        _make(new, "api.py", "def hello() -> str:\n    return 'hi'\n")
        result = runner.invoke(app, ["gate", old, new, "--declared", "patch"])
        assert result.exit_code == 1
        assert "BLOCKED" in result.output


def test_gate_passes_correct_bump():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def hello(name: str) -> str:\n    return name\n")
        _make(new, "api.py", "def hello() -> str:\n    return 'hi'\n")
        result = runner.invoke(app, ["gate", old, new, "--declared", "major"])
        assert result.exit_code == 0
        assert "passed" in result.output


def test_class_attr_removed_is_major():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "m.py", "class User:\n    name: str\n    email: str\n")
        _make(new, "m.py", "class User:\n    name: str\n")
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["kind"] == "attr_removed" and c["level"] == "major" for c in changes)


def test_return_type_changed_is_major():
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", "def count() -> int:\n    return 1\n")
        _make(new, "api.py", "def count() -> str:\n    return '1'\n")
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["kind"] == "return_type_changed" and c["level"] == "major" for c in changes)
        assert max_level(changes) == "major"

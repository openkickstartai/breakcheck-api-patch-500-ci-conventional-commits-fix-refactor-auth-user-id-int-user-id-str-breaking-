"""Tests for BreakCheck — core detection, gate logic, and public API surface discovery."""

import tempfile
from pathlib import Path
from typer.testing import CliRunner
from analyzer import extract_api, diff_api, max_level
from surface import discover_public_api
import ast

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


# ============================================================
# Public API surface discovery tests
# ============================================================

def test_dunder_all_filters_non_public():
    """Deleting a function NOT in __all__ must NOT be reported as breaking."""
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", (
            "__all__ = ['Foo']\n"
            "def Foo() -> str:\n    return 'foo'\n"
            "def Bar() -> str:\n    return 'bar'\n"
        ))
        _make(new, "api.py", (
            "__all__ = ['Foo']\n"
            "def Foo() -> str:\n    return 'foo'\n"
        ))
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert not any(c["kind"] == "function_removed" for c in changes)


def test_private_func_change_not_breaking():
    """Changing _private_func signature must not be reported."""
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", (
            "def public_fn() -> str:\n    return 'ok'\n"
            "def _private_fn(x: int) -> str:\n    return str(x)\n"
        ))
        _make(new, "api.py", (
            "def public_fn() -> str:\n    return 'ok'\n"
            "def _private_fn(x: str, y: int) -> str:\n    return x\n"
        ))
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert not any('_private_fn' in c.get("symbol", "") for c in changes)


def test_breakcheck_ignore_skips_symbol():
    """Symbol marked with # breakcheck: ignore must not trigger changes."""
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", (
            "def stable() -> str:\n    return 'ok'\n"
            "def experimental(x: int) -> str:  # breakcheck: ignore\n    return str(x)\n"
        ))
        _make(new, "api.py", (
            "def stable() -> str:\n    return 'ok'\n"
        ))
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert not any('experimental' in c.get("symbol", "") for c in changes)


def test_breakcheck_public_forces_inclusion():
    """_ prefixed name with # breakcheck: public must be treated as public API."""
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", (
            "def _special(x: int) -> str:  # breakcheck: public\n    return str(x)\n"
        ))
        _make(new, "api.py", (
            "def _special(x: str) -> str:  # breakcheck: public\n    return x\n"
        ))
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["level"] == "major" and '_special' in c.get("symbol", "") for c in changes)


def test_init_reexport_detected():
    """from .sub import Foo in __init__.py must make Foo part of public API."""
    with tempfile.TemporaryDirectory() as d:
        pkg = Path(d) / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("from .sub import Foo\nfrom .sub import Bar\n")
        (pkg / "sub.py").write_text("class Foo:\n    pass\nclass Bar:\n    pass\n")
        tree = ast.parse((pkg / "__init__.py").read_text())
        public = discover_public_api(tree, str(pkg / "__init__.py"))
        assert "Foo" in public
        assert "Bar" in public


def test_dunder_all_removal_is_breaking():
    """Function listed in __all__ that gets removed IS a breaking change."""
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", (
            "__all__ = ['create', 'delete']\n"
            "def create() -> None:\n    pass\n"
            "def delete() -> None:\n    pass\n"
        ))
        _make(new, "api.py", (
            "__all__ = ['create']\n"
            "def create() -> None:\n    pass\n"
        ))
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert any(c["level"] == "major" and c["kind"] == "function_removed" for c in changes)


def test_breakcheck_ignore_overrides_dunder_all():
    """# breakcheck: ignore must override __all__ inclusion."""
    with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
        _make(old, "api.py", (
            "__all__ = ['stable', 'experimental']\n"
            "def stable() -> str:\n    return 'ok'\n"
            "def experimental(x: int) -> str:  # breakcheck: ignore\n    return str(x)\n"
        ))
        _make(new, "api.py", (
            "__all__ = ['stable']\n"
            "def stable() -> str:\n    return 'ok'\n"
        ))
        changes = diff_api(extract_api(Path(old)), extract_api(Path(new)))
        assert not any('experimental' in c.get("symbol", "") for c in changes)

"""Architectural guardrails from BUILD_SPEC §20.1 and §6."""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "trackboard"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


def test_agents_do_not_import_routes():
    """Agents must run headless on a cron server with no web app present."""
    agents_dir = SRC / "agents"
    for path in agents_dir.rglob("*.py"):
        for mod in _imports(path):
            assert "routes" not in mod, f"{path.name} imports {mod}"
            assert "fastapi" not in mod, f"{path.name} imports {mod}"


def test_no_orm_dependency():
    pyproject = (SRC.parents[1] / "pyproject.toml").read_text().lower()
    for banned in ("sqlalchemy", "django", "tortoise", "peewee"):
        assert banned not in pyproject, f"{banned} is banned by spec §4"


def test_only_db_module_touches_sqlite3():
    for path in SRC.rglob("*.py"):
        if path.name == "db.py":
            continue
        assert "sqlite3" not in _imports(path), f"{path.name} bypasses db.py"

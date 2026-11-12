"""Derive the expected schema from Alembic revision files.

Pure and offline: only revision scripts are parsed, never a database. Operations
are read from ``upgrade()`` only (``downgrade()`` mirrors them and must not be
applied), in revision order, and applied net-effect:

    create_table  -> add
    rename_table  -> rename (add the new name if the old one was unknown)
    drop_table    -> remove

The ORM metadata set is computed lazily by :func:`orm_table_names` because it
needs the application models; that import creates an engine object but opens no
connection.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Revision:
    path: Path
    revision: str
    down_revision: str | None
    creates: tuple[str, ...] = ()
    drops: tuple[str, ...] = ()
    renames: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TableComparison:
    expected_count: int
    actual_count: int
    missing: frozenset[str] = frozenset()
    unexpected: frozenset[str] = frozenset()

    @property
    def matches(self) -> bool:
        return not self.missing and not self.unexpected


def _constant_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _assignment_target(node: ast.stmt) -> str | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name):
            return target.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id
    return None


def _operator_calls(function_node: ast.FunctionDef) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    creates: list[str] = []
    drops: list[str] = []
    renames: list[tuple[str, str]] = []
    for node in ast.walk(function_node):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attribute = node.func.attr
        if attribute == "create_table":
            name = _constant_str(node.args[0]) if node.args else None
            if name:
                creates.append(name)
        elif attribute == "drop_table":
            name = _constant_str(node.args[0]) if node.args else None
            if name:
                drops.append(name)
        elif attribute == "rename_table" and len(node.args) >= 2:
            old = _constant_str(node.args[0])
            new = _constant_str(node.args[1])
            if old and new:
                renames.append((old, new))
    return creates, drops, renames


def read_revision(path: str | Path) -> Revision:
    """Parse one revision file without importing or executing it."""
    path = Path(path)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    revision: str | None = None
    down_revision: str | None = None
    upgrade_node: ast.FunctionDef | None = None

    for node in tree.body:
        target = _assignment_target(node)
        if target == "revision":
            revision = _constant_str(node.value)
        elif target == "down_revision":
            value = node.value
            if isinstance(value, ast.Constant):
                down_revision = value.value if isinstance(value.value, str) else None
            elif isinstance(value, (ast.List, ast.Tuple)) and value.elts:
                down_revision = _constant_str(value.elts[0])
            else:
                down_revision = None
        elif isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            upgrade_node = node

    if revision is None:
        raise ValueError(f"revision file without a revision id: {path.name}")

    creates, drops, renames = (
        _operator_calls(upgrade_node) if upgrade_node is not None else ([], [], [])
    )
    return Revision(
        path=path,
        revision=revision,
        down_revision=down_revision,
        creates=tuple(creates),
        drops=tuple(drops),
        renames=tuple(renames),
    )


def discover_revision_paths(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    return sorted(
        path
        for path in directory.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith(".")
    )


def order_revisions(paths: Iterable[str | Path]) -> list[Revision]:
    """Order revisions by their down_revision chain (oldest first)."""
    revisions = [read_revision(path) for path in paths]
    remaining = {revision.revision: revision for revision in revisions}
    ordered: list[Revision] = []
    applied: set[str] = set()

    while remaining:
        progressed = False
        for revision_id, revision in list(remaining.items()):
            if revision.down_revision is None or revision.down_revision in applied:
                ordered.append(revision)
                applied.add(revision_id)
                del remaining[revision_id]
                progressed = True
        if not progressed:
            # Broken chain (missing parent or branch): fall back deterministically.
            ordered.extend(sorted(remaining.values(), key=lambda item: item.revision))
            break
    return ordered


def expected_tables(paths: Iterable[str | Path]) -> set[str]:
    tables: set[str] = set()
    for revision in order_revisions(paths):
        for name in revision.creates:
            tables.add(name)
        for old, new in revision.renames:
            tables.discard(old)
            tables.add(new)
        for name in revision.drops:
            tables.discard(name)
    return tables


def expected_head_revision(paths: Iterable[str | Path]) -> str | None:
    revisions = order_revisions(paths)
    if not revisions:
        return None
    parents = {revision.down_revision for revision in revisions if revision.down_revision}
    heads = [revision.revision for revision in revisions if revision.revision not in parents]
    return heads[0] if len(heads) == 1 else None


def orm_table_names() -> set[str]:
    """Table names declared by the ORM (imports models; opens no connection)."""
    from backend.app import models  # noqa: F401 - register metadata
    from backend.app.database import Base

    return set(Base.metadata.tables.keys())


def compare_tables(expected: Iterable[str], actual: Iterable[str]) -> TableComparison:
    expected_set = set(expected)
    actual_set = set(actual)
    return TableComparison(
        expected_count=len(expected_set),
        actual_count=len(actual_set),
        missing=frozenset(expected_set - actual_set),
        unexpected=frozenset(actual_set - expected_set),
    )

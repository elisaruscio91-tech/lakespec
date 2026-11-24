"""Change classification: what kind of break is this, and what version bump.

The taxonomy is borrowed from schema registries rather than invented, because
Avro and Protobuf settled this fifteen years ago and data teams already know it.
One category is added that schema registries do not have, and it is the one that
actually hurts:

    SEMANTIC -- name and type are unchanged, meaning is not.

Nothing in a type system catches that. If someone redefines revenue to exclude
VAT, every schema check passes and every dashboard quietly starts lying. So a
change to a metric expression is a major bump here, and it carries a migration
note. Treating this as a first-class category is the single most useful thing
this module does.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from lakespec.plan.model import Column, LogicalPlan, Table

# Widening is safe; narrowing is not. Values are rank within a family.
_NUMERIC_WIDTH = {"integer": 1, "number": 2}
_TEMPORAL_WIDTH = {"date": 1, "timestamp": 2}


class Compatibility(str, Enum):
    BACKWARD = "backward"
    """New readers handle old data. Additive: a nullable column, a new enum value."""

    FORWARD = "forward"
    """Old readers handle new data. Removal of something optional."""

    BREAKING = "breaking"
    """Structural break. A consumer will fail or silently lose data."""

    SEMANTIC = "semantic"
    """Structure identical, meaning changed. The dangerous one."""

    @property
    def bump(self) -> str:
        return "minor" if self is Compatibility.BACKWARD else "major"


@dataclass(frozen=True)
class Change:
    compatibility: Compatibility
    subject: str
    summary: str
    detail: str | None = None
    migration: str | None = None

    @property
    def blocking(self) -> bool:
        return self.compatibility in (Compatibility.BREAKING, Compatibility.SEMANTIC)

    def __str__(self) -> str:
        return f"[{self.compatibility.value}] {self.subject}: {self.summary}"


def _type_change(old: Column, new: Column) -> Compatibility:
    o, n = old.logical_type.lower(), new.logical_type.lower()
    if o == n:
        return Compatibility.BACKWARD
    for family in (_NUMERIC_WIDTH, _TEMPORAL_WIDTH):
        if o in family and n in family:
            return Compatibility.BACKWARD if family[n] > family[o] else Compatibility.BREAKING
    return Compatibility.BREAKING


def _compare_column(table: str, old: Column, new: Column) -> list[Change]:
    subject = f"{table}.{old.name}"
    changes: list[Change] = []

    if old.logical_type.lower() != new.logical_type.lower():
        compat = _type_change(old, new)
        changes.append(
            Change(
                compatibility=compat,
                subject=subject,
                summary=f"type {old.logical_type} -> {new.logical_type}",
                detail="widening" if compat is Compatibility.BACKWARD else "narrowing or unrelated type",
                migration=None
                if compat is Compatibility.BACKWARD
                else "expand/contract: add the new column alongside, dual-write, migrate consumers, then drop",
            )
        )

    if new.required and not old.required:
        changes.append(
            Change(
                compatibility=Compatibility.BREAKING,
                subject=subject,
                summary="became required",
                detail="existing rows may hold nulls",
                migration="backfill first, then tighten the contract",
            )
        )
    elif old.required and not new.required:
        changes.append(
            Change(
                compatibility=Compatibility.FORWARD,
                subject=subject,
                summary="no longer required",
                detail="consumers assuming non-null will break",
            )
        )

    if old.is_primary_key != new.is_primary_key:
        changes.append(
            Change(
                compatibility=Compatibility.BREAKING,
                subject=subject,
                summary="primary key membership changed",
                detail="the grain of the table changes, so every downstream aggregate changes",
                migration="treat as a new table, not an edit",
            )
        )

    old_values = {v for v, _ in old.allowed_values}
    new_values = {v for v, _ in new.allowed_values}
    if old_values and new_values:
        if removed := old_values - new_values:
            changes.append(
                Change(
                    compatibility=Compatibility.BREAKING,
                    subject=subject,
                    summary=f"allowed values removed: {sorted(removed)}",
                    detail="existing rows may hold values the contract no longer permits",
                )
            )
        if added := new_values - old_values:
            changes.append(
                Change(
                    compatibility=Compatibility.BACKWARD,
                    subject=subject,
                    summary=f"allowed values added: {sorted(added)}",
                )
            )

    if old.classification != new.classification:
        loosened = old.classification == "restricted" and new.classification != "restricted"
        changes.append(
            Change(
                compatibility=Compatibility.SEMANTIC if loosened else Compatibility.BACKWARD,
                subject=subject,
                summary=f"classification {old.classification} -> {new.classification}",
                detail="data previously withheld from agents and reports would become visible"
                if loosened
                else None,
                migration="requires explicit human ratification: this is a disclosure decision, "
                "not a schema edit"
                if loosened
                else None,
            )
        )

    old_sql = old.transform.sql if old.transform else None
    new_sql = new.transform.sql if new.transform else None
    if old_sql and new_sql and old_sql != new_sql:
        changes.append(
            Change(
                compatibility=Compatibility.SEMANTIC,
                subject=subject,
                summary="derivation logic changed",
                detail="same name, same type, different numbers; no type check catches this",
                migration="recompute history or version the column, and tell every consumer",
            )
        )

    return changes


def _compare_table(old: Table, new: Table) -> list[Change]:
    changes: list[Change] = []
    old_cols = {c.name: c for c in old.columns}
    new_cols = {c.name: c for c in new.columns}

    for name in new_cols.keys() - old_cols.keys():
        col = new_cols[name]
        changes.append(
            Change(
                compatibility=Compatibility.BREAKING if col.required else Compatibility.BACKWARD,
                subject=f"{old.name}.{name}",
                summary="column added" + (" as required" if col.required else ""),
                detail="a required column cannot be added to data that already exists"
                if col.required
                else "lands in bronze and stays quarantined until accepted into the contract",
            )
        )

    for name in old_cols.keys() - new_cols.keys():
        col = old_cols[name]
        changes.append(
            Change(
                compatibility=Compatibility.BREAKING
                if (col.required or col.is_primary_key)
                else Compatibility.FORWARD,
                subject=f"{old.name}.{name}",
                summary="column removed",
                migration="expand/contract: deprecate with an end-of-life date, then drop",
            )
        )

    for name in old_cols.keys() & new_cols.keys():
        changes.extend(_compare_column(old.name, old_cols[name], new_cols[name]))

    if old.granularity and new.granularity and old.granularity != new.granularity:
        changes.append(
            Change(
                compatibility=Compatibility.SEMANTIC,
                subject=old.name,
                summary="declared grain changed",
                detail="every count and every sum over this table changes meaning",
            )
        )

    return changes


def classify_changes(old: LogicalPlan, new: LogicalPlan) -> list[Change]:
    """Diff two plans and classify every change. Order: worst first."""
    changes: list[Change] = []
    old_tables = {t.name: t for t in old.tables}
    new_tables = {t.name: t for t in new.tables}

    for name in new_tables.keys() - old_tables.keys():
        changes.append(
            Change(Compatibility.BACKWARD, name, "table added")
        )
    for name in old_tables.keys() - new_tables.keys():
        changes.append(
            Change(
                Compatibility.BREAKING,
                name,
                "table removed",
                migration="expand/contract: deprecate, migrate consumers, then drop",
            )
        )
    for name in old_tables.keys() & new_tables.keys():
        changes.extend(_compare_table(old_tables[name], new_tables[name]))

    old_metrics = {m.name: m for m in old.metrics}
    new_metrics = {m.name: m for m in new.metrics}

    for name in new_metrics.keys() - old_metrics.keys():
        changes.append(Change(Compatibility.BACKWARD, f"metric {name}", "metric added"))
    for name in old_metrics.keys() - new_metrics.keys():
        changes.append(
            Change(
                Compatibility.BREAKING,
                f"metric {name}",
                "metric removed",
                detail="dashboards and saved questions referencing it will fail",
            )
        )
    for name in old_metrics.keys() & new_metrics.keys():
        if old_metrics[name].sql != new_metrics[name].sql:
            changes.append(
                Change(
                    compatibility=Compatibility.SEMANTIC,
                    subject=f"metric {name}",
                    summary="definition changed",
                    detail="this is metric drift: the number moves while nothing in the schema does",
                    migration="major bump plus an effective-from date; keep the old definition "
                    "available for historical comparison",
                )
            )

    old_joins = {(j.from_table, j.to_table): j for j in old.joins}
    new_joins = {(j.from_table, j.to_table): j for j in new.joins}
    for key in old_joins.keys() - new_joins.keys():
        changes.append(
            Change(
                Compatibility.BREAKING,
                f"join {key[0]} -> {key[1]}",
                "join path removed",
                detail="a query compiler can no longer connect these tables, "
                "and an agent would be left to guess",
            )
        )
    for key in new_joins.keys() - old_joins.keys():
        changes.append(Change(Compatibility.BACKWARD, f"join {key[0]} -> {key[1]}", "join path added"))

    order = {
        Compatibility.SEMANTIC: 0,
        Compatibility.BREAKING: 1,
        Compatibility.FORWARD: 2,
        Compatibility.BACKWARD: 3,
    }
    return sorted(changes, key=lambda c: (order[c.compatibility], c.subject))


def next_version(current: str, changes: list[Change]) -> str:
    """Semver bump implied by a change set. No changes means no bump."""
    if not changes:
        return current
    try:
        major, minor, _patch = (int(p) for p in current.split(".")[:3])
    except ValueError:
        return current
    if any(c.compatibility.bump == "major" for c in changes):
        return f"{major + 1}.0.0"
    return f"{major}.{minor + 1}.0"

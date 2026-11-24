"""The logical plan: lakespec's engine-neutral intermediate representation.

This module is why adapters are cheap to write. It must never import an engine,
a driver or a cloud SDK. If you find yourself reaching for one here, the
abstraction has leaked and the same contract no longer compiles everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Classification = Literal["public", "internal", "restricted"]
Layer = Literal["bronze", "silver", "gold"]


@dataclass(frozen=True)
class QualityRule:
    """A single assertion, lifted from ODCS `quality`."""

    metric: str
    dimension: str | None = None
    must_be: Any | None = None
    must_be_greater_than: Any | None = None
    must_be_less_than: Any | None = None
    must_be_between: tuple[Any, Any] | None = None
    schedule: str | None = None
    scope: Literal["table", "column"] = "column"


@dataclass(frozen=True)
class Transform:
    """How a column is derived. Lifted from ODCS transform* keys."""

    sql: str
    source_objects: tuple[str, ...] = ()
    note: str | None = None


@dataclass
class Column:
    name: str
    logical_type: str
    physical_type: str | None = None
    physical_name: str | None = None
    description: str | None = None
    label: str | None = None
    required: bool = False
    unique: bool = False
    primary_key_position: int | None = None
    partition_position: int | None = None
    classification: Classification | None = None
    critical: bool = False
    allowed_values: tuple[tuple[str, str], ...] = ()
    examples: tuple[Any, ...] = ()
    transform: Transform | None = None
    quality: tuple[QualityRule, ...] = ()
    is_time: bool = False
    synonyms: tuple[str, ...] = ()

    @property
    def is_primary_key(self) -> bool:
        return self.primary_key_position is not None

    @property
    def agent_visible(self) -> bool:
        """Restricted columns are withheld from agent-facing context by default.

        This is a safety default, not a security boundary: the adapter is still
        responsible for enforcement in the target engine.
        """
        return self.classification != "restricted"


@dataclass
class Metric:
    name: str
    sql: str
    description: str | None = None
    datatype: str | None = None
    dataset: str | None = None
    synonyms: tuple[str, ...] = ()
    instructions: str | None = None
    owner: str | None = None
    effective_from: str | None = None


@dataclass
class JoinEdge:
    name: str
    from_table: str
    to_table: str
    from_columns: tuple[str, ...]
    to_columns: tuple[str, ...]
    cardinality: str | None = None
    instructions: str | None = None


@dataclass
class Table:
    name: str
    physical_name: str | None = None
    business_name: str | None = None
    description: str | None = None
    granularity: str | None = None
    layer: Layer | None = None
    source: str | None = None
    columns: list[Column] = field(default_factory=list)
    quality: tuple[QualityRule, ...] = ()
    tags: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    instructions: str | None = None
    contract_version: str | None = None

    @property
    def primary_key(self) -> list[Column]:
        keys = [c for c in self.columns if c.is_primary_key]
        return sorted(keys, key=lambda c: c.primary_key_position or 0)

    def column(self, name: str) -> Column | None:
        return next((c for c in self.columns if c.name == name), None)


@dataclass
class LogicalPlan:
    """Everything an adapter needs, and nothing about where it will run."""

    name: str
    tables: list[Table] = field(default_factory=list)
    joins: list[JoinEdge] = field(default_factory=list)
    metrics: list[Metric] = field(default_factory=list)
    instructions: str | None = None
    synonyms: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    def table(self, name: str) -> Table | None:
        return next((t for t in self.tables if t.name == name), None)

    def join_path(self, a: str, b: str) -> JoinEdge | None:
        """The declared path between two tables.

        A query compiler must use this rather than letting a model guess a join:
        the declared path is what makes a generated query reproducible and makes
        fan-out double counting detectable instead of silent.
        """
        for e in self.joins:
            if {e.from_table, e.to_table} == {a, b}:
                return e
        return None

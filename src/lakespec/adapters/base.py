"""The adapter contract.

An adapter is a pure function from logical plan to native artefacts. Writing a
new one should take days, not months -- that is the whole point of the plan
sitting in the middle.

Rules for adapter authors:

1. Read the plan, never the YAML. If you need a field the plan does not carry,
   add it to the plan, do not reach back into the contract.
2. Emit text artefacts; do not execute anything in `emit`. Running belongs to
   the host (dbt, Airflow, a cluster, the user's hand). `apply` is optional and
   must stay separable.
3. Declare what you cannot do. An adapter that silently drops quality rules is
   worse than one that refuses.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from lakespec.plan.model import LogicalPlan


@dataclass(frozen=True)
class Artifact:
    """One emitted file. Content is text; the adapter decides the layout."""

    path: str
    content: str
    kind: str = "sql"


@dataclass(frozen=True)
class Capabilities:
    """An honest declaration of what this target supports.

    `lakespec compile` warns for every plan feature the target cannot express,
    rather than emitting something that quietly means less than the contract says.
    """

    transforms: bool = False
    quality_rules: bool = False
    primary_keys: bool = False
    foreign_keys: bool = False
    partitioning: bool = False
    column_descriptions: bool = False
    column_tags: bool = False
    row_level_security: bool = False
    semantic_layer: bool = False
    catalog_registration: bool = False
    notes: tuple[str, ...] = ()


class Adapter(ABC):
    name: str = "abstract"
    capabilities: Capabilities = Capabilities()

    @abstractmethod
    def emit(self, plan: LogicalPlan) -> list[Artifact]:
        """Turn the plan into native artefacts. No side effects."""

    def write(self, plan: LogicalPlan, out_dir: str | Path) -> list[Path]:
        out = Path(out_dir)
        written = []
        for artifact in self.emit(plan):
            target = out / artifact.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(artifact.content, encoding="utf-8")
            written.append(target)
        return written

    def unsupported(self, plan: LogicalPlan) -> list[str]:
        """Plan features this target will not carry. Reported, never hidden."""
        gaps: list[str] = []
        caps = self.capabilities
        if not caps.transforms and any(c.transform for t in plan.tables for c in t.columns):
            gaps.append("column transforms are declared but this target does not emit them")
        if not caps.quality_rules and any(
            t.quality or any(c.quality for c in t.columns) for t in plan.tables
        ):
            gaps.append("quality rules are declared but this target does not emit them")
        if not caps.foreign_keys and plan.joins:
            gaps.append("join edges are declared but this target cannot enforce them")
        if not caps.semantic_layer and plan.metrics:
            gaps.append("metrics are declared but this target has no semantic layer to hold them")
        if not caps.column_tags and any(
            c.classification == "restricted" for t in plan.tables for c in t.columns
        ):
            gaps.append(
                "restricted columns are declared but this target cannot tag them; "
                "enforcement must happen elsewhere"
            )
        return gaps


@dataclass
class AdapterRegistry:
    adapters: dict[str, type[Adapter]] = field(default_factory=dict)

    def register(self, adapter: type[Adapter]) -> type[Adapter]:
        self.adapters[adapter.name] = adapter
        return adapter

    def get(self, name: str) -> Adapter:
        if name not in self.adapters:
            known = ", ".join(sorted(self.adapters)) or "none"
            raise KeyError(f"unknown adapter {name!r}; registered: {known}")
        return self.adapters[name]()

    def names(self) -> list[str]:
        return sorted(self.adapters)


registry = AdapterRegistry()

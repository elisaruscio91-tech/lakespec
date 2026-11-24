"""Loading ODCS contracts and OSI semantic models.

lakespec does not define a format. It reads two open standards:

  * ODCS  -- Open Data Contract Standard, Bitol / LF AI & Data
  * OSI   -- Open Semantic Interchange, now Apache Ossie (incubating)

Both are YAML and Apache-2.0 licensed. Keeping to them is a deliberate choice:
an orphan in-house format would be the fastest way to make this project
unadoptable, and both standards already carry the fields we need.

Validation here is intentionally shallow -- enough to fail with a useful message.
Deep validation belongs against each standard's own JSON Schema, and the ODCS
docs warn that where the schema and the written standard disagree, the standard
wins. So do not build hard assumptions on the schema in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class SpecError(ValueError):
    """A contract or semantic model that cannot be used as given."""


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"{path}: not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SpecError(f"{path}: expected a mapping at the top level")
    return data


def load_contract(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    doc = _read_yaml(path)
    if doc.get("kind") != "DataContract":
        raise SpecError(f"{path}: expected kind: DataContract, got {doc.get('kind')!r}")
    if not doc.get("schema"):
        raise SpecError(f"{path}: contract has no schema section")
    doc["__path__"] = str(path)
    return doc


def load_semantic_model(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    doc = _read_yaml(path)
    if not doc.get("datasets"):
        raise SpecError(f"{path}: OSI model has no datasets")
    doc["__path__"] = str(path)
    return doc


@dataclass
class SpecBundle:
    """One semantic model plus the contracts it is built on."""

    semantic_model: dict[str, Any]
    contracts: list[dict[str, Any]] = field(default_factory=list)

    @property
    def name(self) -> str:
        return str(self.semantic_model.get("name", "unnamed"))

    @property
    def sources(self) -> tuple[str, ...]:
        paths = [c.get("__path__", "?") for c in self.contracts]
        paths.append(self.semantic_model.get("__path__", "?"))
        return tuple(paths)


def load_bundle(semantic_model_path: str | Path) -> SpecBundle:
    """Load a semantic model and follow its declared contract references.

    The reference lives under OSI's `custom_extensions.lakespec.contracts`, as
    paths relative to the model file. OSI reserves `custom_extensions` for
    exactly this, so we extend the standard instead of forking it.
    """
    model_path = Path(semantic_model_path)
    model = load_semantic_model(model_path)
    refs = (
        model.get("custom_extensions", {})
        .get("lakespec", {})
        .get("contracts", [])
    )
    contracts = []
    for ref in refs:
        candidate = (model_path.parent / ref).resolve()
        if not candidate.exists():
            raise SpecError(f"{model_path}: referenced contract not found: {ref}")
        contracts.append(load_contract(candidate))
    return SpecBundle(semantic_model=model, contracts=contracts)

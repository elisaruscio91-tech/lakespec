"""Tests that run with no infrastructure. That is the point of the DuckDB target.

Keep it that way: a test that needs a cluster is a test nobody runs.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from lakespec.adapters import registry
from lakespec.compat import Compatibility, classify_changes, next_version
from lakespec.mcp.context import build_agent_context
from lakespec.plan import build_plan
from lakespec.spec import SpecBundle, load_bundle

EXAMPLE = Path(__file__).parent.parent / "examples/retail/semantics/sales.osi.yaml"


@pytest.fixture
def bundle() -> SpecBundle:
    return load_bundle(EXAMPLE)


@pytest.fixture
def plan(bundle: SpecBundle):
    return build_plan(bundle)


def test_contracts_are_followed_from_the_model(bundle: SpecBundle):
    assert {c["name"] for c in bundle.contracts} == {"orders", "customers"}


def test_primary_key_order_comes_from_position(plan):
    assert [c.name for c in plan.table("orders").primary_key] == ["order_id"]


def test_transform_keys_become_lineage(plan):
    net = plan.table("orders").column("net_amount")
    assert net.transform is not None
    assert set(net.transform.source_objects) == {"bronze.raw_orders", "bronze.raw_order_discounts"}


def test_join_edge_is_declared_once_from_both_standards(plan):
    """ODCS gives the cardinality, OSI gives the name. One edge, not two."""
    assert len(plan.joins) == 1
    edge = plan.join_path("orders", "customers")
    assert edge.name == "orders_to_customers"
    assert edge.cardinality == "many-to-one"


def test_restricted_columns_are_withheld_from_agent_context(plan):
    context = build_agent_context(plan)
    customers = next(t for t in context["tables"] if t["name"] == "customers")
    assert "tax_id" in customers["withheld_columns"]
    assert all(col["name"] != "tax_id" for col in customers["columns"])


def test_agent_context_never_offers_raw_sql(plan):
    context = build_agent_context(plan)
    assert "Do not write SQL" in context["query_protocol"]["note"]
    assert any("Never invent a join" in rule for rule in context["rules"])


def test_duckdb_adapter_emits_and_declares_its_gaps(plan, tmp_path):
    adapter = registry.get("duckdb")
    written = adapter.write(plan, tmp_path)
    names = {p.relative_to(tmp_path).as_posix() for p in written}
    assert "ddl/orders.sql" in names
    assert "silver/orders.sql" in names
    assert "quality/checks.sql" in names
    gaps = adapter.unsupported(plan)
    assert any("restricted" in g for g in gaps), "a target that cannot tag PII must say so"


@pytest.mark.parametrize("name", ["spark_dbt", "postgres_pglake", "databricks"])
def test_declared_but_unimplemented_adapters_refuse_loudly(plan, name):
    with pytest.raises(NotImplementedError):
        registry.get(name).emit(plan)


def test_metric_redefinition_is_semantic_not_backward(bundle, plan):
    """The change no type system catches, and the reason this module exists."""
    other = copy.deepcopy(bundle)
    metric = other.semantic_model["datasets"][0]["metrics"][0]
    metric["expression"]["dialects"][0]["expression"] = "SUM(net_amount * 1.22)"
    changes = classify_changes(plan, build_plan(other))
    assert [c.compatibility for c in changes] == [Compatibility.SEMANTIC]
    assert changes[0].blocking


def test_widening_a_type_is_backward_narrowing_is_breaking(bundle, plan):
    wider = copy.deepcopy(bundle)
    wider.contracts[0]["schema"][0]["properties"][2]["logicalType"] = "timestamp"
    assert classify_changes(plan, build_plan(wider))[0].compatibility is Compatibility.BACKWARD

    narrower = copy.deepcopy(bundle)
    narrower.contracts[0]["schema"][0]["properties"][4]["logicalType"] = "integer"
    assert classify_changes(plan, build_plan(narrower))[0].compatibility is Compatibility.BREAKING


def test_loosening_a_classification_requires_ratification(bundle, plan):
    loosened = copy.deepcopy(bundle)
    loosened.contracts[1]["schema"][0]["properties"][3]["classification"] = "public"
    change = classify_changes(plan, build_plan(loosened))[0]
    assert change.compatibility is Compatibility.SEMANTIC
    assert "ratification" in (change.migration or "")


def test_new_optional_column_is_quarantined_not_breaking(bundle, plan):
    added = copy.deepcopy(bundle)
    added.contracts[0]["schema"][0]["properties"].append(
        {"name": "channel", "logicalType": "string", "required": False}
    )
    change = classify_changes(plan, build_plan(added))[0]
    assert change.compatibility is Compatibility.BACKWARD
    assert "quarantined" in (change.detail or "")


def test_version_bump_follows_the_worst_change():
    from lakespec.compat.classify import Change

    assert next_version("1.2.0", []) == "1.2.0"
    assert next_version("1.2.0", [Change(Compatibility.BACKWARD, "x", "added")]) == "1.3.0"
    assert next_version("1.2.0", [Change(Compatibility.SEMANTIC, "x", "redefined")]) == "2.0.0"


def test_restricted_join_key_is_structural_not_hidden(plan):
    """Hiding a join key while publishing its join path would be incoherent."""
    context = build_agent_context(plan)
    orders = next(t for t in context["tables"] if t["name"] == "orders")
    customer_id = next(c for c in orders["columns"] if c["name"] == "customer_id")
    assert customer_id["join_key_only"] is True
    assert "customer_id" not in orders["withheld_columns"]
    assert any("join_key_only" in rule for rule in context["rules"])

"""Fold an ODCS + OSI bundle into one logical plan.

This is where the "single artefact, no drift" property is actually earned: the
join graph, the column meanings and the metric definitions are read once and
handed to every downstream emitter -- pipelines, catalog, agent context.
"""

from __future__ import annotations

from typing import Any

from lakespec.plan.model import (
    Column,
    JoinEdge,
    LogicalPlan,
    Metric,
    QualityRule,
    Table,
    Transform,
)
from lakespec.spec.load import SpecBundle


def _custom(props: list[dict[str, Any]] | None, key: str) -> Any:
    for entry in props or []:
        if entry.get("property") == key:
            return entry.get("value")
    return None


def _quality(raw: list[dict[str, Any]] | None, scope: str) -> tuple[QualityRule, ...]:
    rules = []
    for item in raw or []:
        between = item.get("mustBeBetween")
        rules.append(
            QualityRule(
                metric=item.get("metric", "unknown"),
                dimension=item.get("dimension"),
                must_be=item.get("mustBe"),
                must_be_greater_than=item.get("mustBeGreaterThan"),
                must_be_less_than=item.get("mustBeLessThan"),
                must_be_between=tuple(between) if between else None,
                schedule=item.get("schedule"),
                scope=scope,  # type: ignore[arg-type]
            )
        )
    return tuple(rules)


def _column(prop: dict[str, Any]) -> Column:
    transform = None
    if prop.get("transformLogic"):
        transform = Transform(
            sql=prop["transformLogic"],
            source_objects=tuple(prop.get("transformSourceObjects") or ()),
            note=prop.get("transformDescription"),
        )
    allowed = tuple(
        (str(e.get("value")), str(e.get("label", e.get("value"))))
        for e in prop.get("enum") or []
    )
    position = prop.get("primaryKeyPosition")
    return Column(
        name=prop["name"],
        logical_type=prop.get("logicalType", "string"),
        physical_type=prop.get("physicalType"),
        physical_name=prop.get("physicalName"),
        description=prop.get("description"),
        required=bool(prop.get("required", False)),
        unique=bool(prop.get("unique", False)),
        primary_key_position=position if prop.get("primaryKey") and position and position > 0 else None,
        partition_position=prop.get("partitionKeyPosition") if prop.get("partitioned") else None,
        classification=prop.get("classification"),
        critical=bool(prop.get("criticalDataElement", False)),
        allowed_values=allowed,
        examples=tuple(prop.get("examples") or ()),
        transform=transform,
        quality=_quality(prop.get("quality"), scope="column"),
    )


def _relationship_edges(obj: dict[str, Any], table_name: str) -> list[JoinEdge]:
    """Read both ODCS relationship forms into one edge list.

    Property level carries `to` only; schema level carries `from` and `to` and is
    the form that handles composite keys.
    """
    edges: list[JoinEdge] = []

    for rel in obj.get("relationships") or []:
        if rel.get("type") != "foreignKey":
            continue
        frm = rel.get("from")
        to = rel.get("to")
        frm_list = frm if isinstance(frm, list) else [frm]
        to_list = to if isinstance(to, list) else [to]
        from_table = frm_list[0].split(".")[0] if frm_list and frm_list[0] else table_name
        to_table = to_list[0].split(".")[0] if to_list and to_list[0] else "?"
        edges.append(
            JoinEdge(
                name=f"{from_table}_to_{to_table}",
                from_table=from_table,
                to_table=to_table,
                from_columns=tuple(x.split(".")[-1] for x in frm_list if x),
                to_columns=tuple(x.split(".")[-1] for x in to_list if x),
                cardinality=_custom(rel.get("customProperties"), "cardinality"),
            )
        )

    for prop in obj.get("properties") or []:
        for rel in prop.get("relationships") or []:
            if rel.get("type") != "foreignKey" or not rel.get("to"):
                continue
            target = str(rel["to"])
            to_table, _, to_col = target.rpartition(".")
            edges.append(
                JoinEdge(
                    name=f"{table_name}_to_{to_table}",
                    from_table=table_name,
                    to_table=to_table or "?",
                    from_columns=(prop["name"],),
                    to_columns=(to_col or "?",),
                    cardinality=_custom(rel.get("customProperties"), "cardinality"),
                )
            )
    return edges


def _ai_context(node: dict[str, Any]) -> tuple[tuple[str, ...], str | None]:
    ctx = node.get("ai_context")
    if isinstance(ctx, str):
        return (), ctx
    if isinstance(ctx, dict):
        return tuple(ctx.get("synonyms") or ()), ctx.get("instructions")
    return (), None


def _sql(expression: dict[str, Any] | None, dialect: str = "ANSI_SQL") -> str:
    """Pull SQL out of an OSI expression.

    OSI allows a primary `sql` form plus a list of dialect-specific forms. We
    prefer an exact dialect match, then ANSI, then whatever is there.
    """
    if not expression:
        return ""
    if expression.get("sql"):
        return str(expression["sql"])
    dialects = expression.get("dialects") or []
    for want in (dialect, "ANSI_SQL"):
        for entry in dialects:
            if entry.get("dialect") == want:
                return str(entry.get("expression", ""))
    return str(dialects[0].get("expression", "")) if dialects else ""


def build_plan(bundle: SpecBundle, dialect: str = "ANSI_SQL") -> LogicalPlan:
    model = bundle.semantic_model
    tables: dict[str, Table] = {}
    joins: list[JoinEdge] = []

    for contract in bundle.contracts:
        for obj in contract.get("schema", []):
            name = obj["name"]
            table = Table(
                name=name,
                physical_name=obj.get("physicalName"),
                business_name=obj.get("businessName"),
                description=obj.get("description"),
                granularity=obj.get("dataGranularityDescription"),
                layer=_custom(obj.get("customProperties"), "lakespec.layer"),
                columns=[_column(p) for p in obj.get("properties", [])],
                quality=_quality(obj.get("quality"), scope="table"),
                tags=tuple(obj.get("tags") or ()),
                contract_version=contract.get("version"),
            )
            tables[name] = table
            joins.extend(_relationship_edges(obj, name))

    metrics: list[Metric] = []

    for dataset in model.get("datasets", []):
        name = dataset["name"]
        table = tables.get(name) or Table(name=name)
        tables.setdefault(name, table)
        table.source = dataset.get("source")
        syn, instr = _ai_context(dataset)
        table.synonyms = syn
        table.instructions = instr

        for field_def in dataset.get("fields", []):
            col = table.column(field_def["name"])
            if col is None:
                col = Column(name=field_def["name"], logical_type=field_def.get("datatype", "string"))
                table.columns.append(col)
            col.label = field_def.get("label") or col.label
            col.description = col.description or field_def.get("description")
            dim = field_def.get("dimension")
            col.is_time = bool(isinstance(dim, dict) and dim.get("is_time"))
            f_syn, _ = _ai_context(field_def)
            col.synonyms = f_syn

        for metric in dataset.get("metrics", []):
            m_syn, m_instr = _ai_context(metric)
            metrics.append(
                Metric(
                    name=metric["name"],
                    sql=_sql(metric.get("expression"), dialect),
                    description=metric.get("description"),
                    datatype=metric.get("datatype"),
                    dataset=name,
                    synonyms=m_syn,
                    instructions=m_instr,
                )
            )

    for metric in model.get("metrics", []):
        m_syn, m_instr = _ai_context(metric)
        ext = (metric.get("custom_extensions") or {}).get("lakespec", {})
        metrics.append(
            Metric(
                name=metric["name"],
                sql=_sql(metric.get("expression"), dialect),
                description=metric.get("description"),
                datatype=metric.get("datatype"),
                dataset=None,
                synonyms=m_syn,
                instructions=m_instr,
                owner=ext.get("owner"),
                effective_from=ext.get("effective_from"),
            )
        )

    declared = {(e.from_table, e.to_table, e.from_columns, e.to_columns) for e in joins}
    for rel in model.get("relationships", []):
        key = (
            rel.get("from"),
            rel.get("to"),
            tuple(rel.get("from_columns") or ()),
            tuple(rel.get("to_columns") or ()),
        )
        _, instr = _ai_context(rel)
        if key in declared:
            for edge in joins:
                if (edge.from_table, edge.to_table, edge.from_columns, edge.to_columns) == key:
                    edge.name = rel.get("name", edge.name)
                    edge.instructions = instr
            continue
        joins.append(
            JoinEdge(
                name=rel.get("name", "unnamed"),
                from_table=str(rel.get("from")),
                to_table=str(rel.get("to")),
                from_columns=tuple(rel.get("from_columns") or ()),
                to_columns=tuple(rel.get("to_columns") or ()),
                instructions=instr,
            )
        )

    syn, instr = _ai_context(model)
    return LogicalPlan(
        name=str(model.get("name", "unnamed")),
        tables=list(tables.values()),
        joins=joins,
        metrics=metrics,
        instructions=instr,
        synonyms=syn,
        sources=bundle.sources,
    )

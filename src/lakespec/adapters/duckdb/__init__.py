"""DuckDB adapter -- the reference implementation.

This is not the least important adapter, it is the one that decides whether the
project is adoptable. It must run on a laptop in minutes with no cloud account,
no cluster and no credentials, because that is the only first experience that
earns a contributor. It is also how the compiler gets tested in CI with no
infrastructure at all.

Every other adapter should be read against this one.
"""

from __future__ import annotations

from lakespec.adapters.base import Adapter, Artifact, Capabilities, registry
from lakespec.plan.model import Column, LogicalPlan, QualityRule, Table

_TYPES = {
    "string": "VARCHAR",
    "number": "DECIMAL(18,2)",
    "integer": "BIGINT",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "object": "STRUCT",
    "array": "LIST",
}


def _sql_type(col: Column) -> str:
    if col.physical_type:
        return col.physical_type.upper()
    return _TYPES.get(col.logical_type.lower(), "VARCHAR")


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _ddl(table: Table) -> str:
    lines = [f"CREATE OR REPLACE TABLE {_ident(table.name)} ("]
    parts = []
    for col in table.columns:
        piece = f"  {_ident(col.name)} {_sql_type(col)}"
        if col.required:
            piece += " NOT NULL"
        parts.append(piece)
    pk = table.primary_key
    if pk:
        cols = ", ".join(_ident(c.name) for c in pk)
        parts.append(f"  PRIMARY KEY ({cols})")
    lines.append(",\n".join(parts))
    lines.append(");")
    header = []
    if table.business_name:
        header.append(f"-- {table.business_name}")
    if table.granularity:
        header.append(f"-- grain: {table.granularity}")
    if table.contract_version:
        header.append(f"-- contract version: {table.contract_version}")
    return "\n".join([*header, *lines])


def _silver_select(table: Table) -> str | None:
    """Emit bronze -> silver from the contract's transform keys.

    Columns with no declared transform are passed through by name. Columns with
    one are emitted as written. The source objects come from the contract, which
    is what makes the lineage real rather than a diagram someone drew once.
    """
    derived = [c for c in table.columns if c.transform]
    if not derived:
        return None
    sources: list[str] = []
    for col in table.columns:
        for obj in (col.transform.source_objects if col.transform else ()):
            if obj not in sources:
                sources.append(obj)
    if not sources:
        return None

    select_parts = []
    for col in table.columns:
        if col.transform:
            select_parts.append(f"  {col.transform.sql} AS {_ident(col.name)}")
        else:
            select_parts.append(f"  {_ident(col.name)}")

    base, *rest = sources
    lines = [
        f"-- {table.name}: bronze -> silver, generated from the data contract",
        f"CREATE OR REPLACE VIEW {_ident(table.name + '__silver')} AS",
        "SELECT",
        ",\n".join(select_parts),
        f"FROM {base}",
    ]
    for extra in rest:
        pk = table.primary_key
        on = (
            " AND ".join(f"{base}.{c.name} = {extra}.{c.name}" for c in pk)
            if pk
            else "TRUE /* TODO: no primary key declared, join key unknown */"
        )
        lines.append(f"LEFT JOIN {extra} ON {on}")
    return "\n".join(lines) + ";"


def _quality_query(table: Table, col_name: str | None, rule: QualityRule) -> str | None:
    target = _ident(table.name)
    col = _ident(col_name) if col_name else None
    label = f"{table.name}.{col_name or '*'}:{rule.metric}"

    if rule.metric == "nullValues" and col:
        return (
            f"SELECT '{label}' AS check_name, COUNT(*) AS violations "
            f"FROM {target} WHERE {col} IS NULL"
        )
    if rule.metric == "duplicateCount":
        pk = table.primary_key
        keys = ", ".join(_ident(c.name) for c in pk) if pk else col
        if not keys:
            return None
        return (
            f"SELECT '{label}' AS check_name, COUNT(*) AS violations FROM ("
            f"SELECT {keys} FROM {target} GROUP BY {keys} HAVING COUNT(*) > 1)"
        )
    if rule.metric == "rowCount" and rule.must_be_greater_than is not None:
        return (
            f"SELECT '{label}' AS check_name, "
            f"CASE WHEN COUNT(*) > {rule.must_be_greater_than} THEN 0 ELSE 1 END AS violations "
            f"FROM {target}"
        )
    if rule.metric == "minimum" and col and rule.must_be_greater_than is not None:
        return (
            f"SELECT '{label}' AS check_name, COUNT(*) AS violations "
            f"FROM {target} WHERE {col} <= {rule.must_be_greater_than}"
        )
    return None


def _enum_checks(table: Table) -> list[str]:
    out = []
    for col in table.columns:
        if not col.allowed_values:
            continue
        values = ", ".join(f"'{v}'" for v, _ in col.allowed_values)
        out.append(
            f"SELECT '{table.name}.{col.name}:allowedValues' AS check_name, COUNT(*) AS violations "
            f"FROM {_ident(table.name)} WHERE {_ident(col.name)} IS NOT NULL "
            f"AND {_ident(col.name)} NOT IN ({values})"
        )
    return out


def _metric_views(plan: LogicalPlan) -> str:
    """One view per metric, so the definition exists in exactly one place.

    A dashboard or an agent that computes `fatturato` by any other route is by
    construction wrong, and that is the property worth having.
    """
    blocks = ["-- Metric views generated from the OSI semantic model.", ""]
    for metric in plan.metrics:
        if not metric.sql:
            continue
        name = f"metric__{metric.name}"
        if metric.dataset:
            table = plan.table(metric.dataset)
            source = _ident(table.name) if table else metric.dataset
            blocks.append(f"-- {metric.description or metric.name}")
            blocks.append(
                f"CREATE OR REPLACE VIEW {_ident(name)} AS\n"
                f"SELECT {metric.sql} AS {_ident(metric.name)}\nFROM {source};"
            )
        else:
            blocks.append(
                f"-- {metric.description or metric.name}\n"
                f"-- model-scoped metric: references several datasets, so the join path\n"
                f"-- comes from the declared relationships, never from a guess.\n"
                f"-- TODO(adapter): emit the FROM/JOIN clause from plan.joins."
            )
        blocks.append("")
    return "\n".join(blocks)


@registry.register
class DuckDBAdapter(Adapter):
    name = "duckdb"
    capabilities = Capabilities(
        transforms=True,
        quality_rules=True,
        primary_keys=True,
        foreign_keys=False,
        partitioning=False,
        column_descriptions=False,
        column_tags=False,
        semantic_layer=True,
        catalog_registration=False,
        notes=(
            (
                "DuckDB has no column tags, so `restricted` columns are reported in the "
                "agent context but not enforced in the engine."
            ),
            "Foreign keys are emitted as assertion queries rather than constraints.",
        ),
    )

    def emit(self, plan: LogicalPlan) -> list[Artifact]:
        artifacts: list[Artifact] = []

        for table in plan.tables:
            artifacts.append(
                Artifact(path=f"ddl/{table.name}.sql", content=_ddl(table) + "\n", kind="sql")
            )
            silver = _silver_select(table)
            if silver:
                artifacts.append(
                    Artifact(path=f"silver/{table.name}.sql", content=silver + "\n", kind="sql")
                )

        checks: list[str] = []
        for table in plan.tables:
            for rule in table.quality:
                query = _quality_query(table, None, rule)
                if query:
                    checks.append(query)
            for col in table.columns:
                for rule in col.quality:
                    query = _quality_query(table, col.name, rule)
                    if query:
                        checks.append(query)
            checks.extend(_enum_checks(table))

        for edge in plan.joins:
            on = " AND ".join(
                f"c.{_ident(t)} = p.{_ident(f)}"
                for f, t in zip(edge.from_columns, edge.to_columns, strict=False)
            )
            checks.append(
                f"SELECT '{edge.name}:orphans' AS check_name, COUNT(*) AS violations "
                f"FROM {_ident(edge.from_table)} c "
                f"LEFT JOIN {_ident(edge.to_table)} p ON {on} "
                f"WHERE p.{_ident(edge.to_columns[0])} IS NULL "
                f"AND c.{_ident(edge.from_columns[0])} IS NOT NULL"
            )

        if checks:
            body = "\nUNION ALL\n".join(checks)
            artifacts.append(
                Artifact(
                    path="quality/checks.sql",
                    content=(
                        "-- Quality assertions generated from the data contract.\n"
                        "-- Any row with violations > 0 is a contract breach.\n"
                        f"{body}\nORDER BY violations DESC, check_name;\n"
                    ),
                    kind="sql",
                )
            )

        artifacts.append(
            Artifact(path="semantics/metrics.sql", content=_metric_views(plan), kind="sql")
        )
        return artifacts

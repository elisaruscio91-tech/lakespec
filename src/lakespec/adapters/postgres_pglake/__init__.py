"""Postgres + pg_lake adapter -- declared, not yet implemented.

This is the sovereignty target: Postgres as both the OLTP engine and the Iceberg
catalog, so transactional and analytical data live over one copy in open storage,
inside the customer's own perimeter. pg_lake (Apache-2.0, released November 2025)
provides `CREATE TABLE ... USING iceberg` and executes through DuckDB.

Target shape:

  sql/01_extensions.sql     CREATE EXTENSION pg_lake CASCADE
  sql/10_iceberg/<table>.sql  CREATE TABLE ... USING iceberg, from the contract
  sql/20_silver/<table>.sql   bronze -> silver, from transformLogic
  sql/30_quality/<table>.sql  assertions, optionally as CHECK constraints where
                              the rule is expressible as one
  sql/40_policies/<table>.sql row level security and column privileges derived
                              from `classification`

The interesting part, and the reason this adapter is worth more than the others:
`classification: restricted` can become a real, enforced Postgres column
privilege or RLS policy. On most targets the classification is advisory. Here it
is enforcement, which is exactly what a regulated customer is buying.
"""

from __future__ import annotations

from lakespec.adapters.base import Adapter, Artifact, Capabilities, registry
from lakespec.plan.model import LogicalPlan


@registry.register
class PostgresPgLakeAdapter(Adapter):
    name = "postgres_pglake"
    capabilities = Capabilities(
        transforms=True,
        quality_rules=True,
        primary_keys=True,
        foreign_keys=True,
        partitioning=True,
        column_descriptions=True,
        column_tags=True,
        row_level_security=True,
        semantic_layer=True,
        catalog_registration=True,
        notes=(
            "Not implemented yet. See the module docstring for the target shape.",
            "Postgres acts as the Iceberg catalog, so no external catalog service is required.",
        ),
    )

    def emit(self, plan: LogicalPlan) -> list[Artifact]:
        raise NotImplementedError(
            "The postgres_pglake adapter is declared but not implemented. "
            "Run with --adapter duckdb while this is being built."
        )

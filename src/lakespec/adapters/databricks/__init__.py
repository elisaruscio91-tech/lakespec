"""Databricks + Unity Catalog adapter -- declared, not yet implemented.

This target does not replace anything in a Databricks workspace. It registers
the contract and the semantic model into Unity Catalog, so that definitions used
by notebooks, SQL warehouses and the platform's own agent surface come from the
same source as every other target lakespec compiles to.

Target shape:

  notebooks/silver/<table>.py     PySpark or Spark SQL, from transformLogic
  sql/comments/<table>.sql        COMMENT ON COLUMN from descriptions, so the
                                  meaning lives where the platform reads it
  sql/tags/<table>.sql            SET TAGS from classification, which Unity
                                  Catalog can enforce
  sql/constraints/<table>.sql     PRIMARY KEY / FOREIGN KEY; informational in
                                  Unity Catalog, but the join graph is what a
                                  query planner or agent reads to pick a path
  semantics/<model>.yml           metric definitions and ai_context

Implementation note worth settling before writing code: Unity Catalog tags and
column comments are set through SQL DDL, while semantics registration goes
through the workspace API. Keep the two emissions in separate files so a
customer can apply the DDL without granting API access.
"""

from __future__ import annotations

from lakespec.adapters.base import Adapter, Artifact, Capabilities, registry
from lakespec.plan.model import LogicalPlan


@registry.register
class DatabricksAdapter(Adapter):
    name = "databricks"
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
            "Registers semantics into Unity Catalog rather than replacing the platform.",
        ),
    )

    def emit(self, plan: LogicalPlan) -> list[Artifact]:
        raise NotImplementedError(
            "The databricks adapter is declared but not implemented. "
            "Run with --adapter duckdb while this is being built."
        )

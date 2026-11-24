"""Spark / dbt adapter -- declared, not yet implemented.

Target shape, so a contributor can pick this up without asking:

  models/silver/<table>.sql       one dbt model per table, body from
                                  transformLogic + transformSourceObjects
  models/silver/<table>.yml       dbt model contract: columns, data_type,
                                  not_null and unique tests from ODCS quality,
                                  relationships test from the join edges
  models/semantics/<metric>.sql   one model per metric, join path from plan.joins
  macros/lakespec_tags.sql        column tagging where the warehouse supports it

Open question to settle before writing code: do we emit dbt model contracts
(declarative, enforced by dbt) or plain models plus schema tests? The former is
closer to ODCS semantics; the latter works on older dbt versions. Pick one and
write it in a decision record, do not support both.
"""

from __future__ import annotations

from lakespec.adapters.base import Adapter, Artifact, Capabilities, registry
from lakespec.plan.model import LogicalPlan


@registry.register
class SparkDbtAdapter(Adapter):
    name = "spark_dbt"
    capabilities = Capabilities(
        transforms=True,
        quality_rules=True,
        primary_keys=True,
        foreign_keys=True,
        partitioning=True,
        column_descriptions=True,
        column_tags=False,
        semantic_layer=True,
        catalog_registration=False,
        notes=("Not implemented yet. See the module docstring for the target shape.",),
    )

    def emit(self, plan: LogicalPlan) -> list[Artifact]:
        raise NotImplementedError(
            "The spark_dbt adapter is declared but not implemented. "
            "Run with --adapter duckdb, or read src/lakespec/adapters/spark_dbt/__init__.py "
            "and open a PR -- the logical plan is stable, so this is a contained job."
        )

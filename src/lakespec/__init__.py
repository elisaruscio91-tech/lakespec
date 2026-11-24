"""lakespec: compile data contracts into pipelines, catalog metadata and agent context.

The contract is the source of truth. Everything else is emitted from it.
"""

__version__ = "0.0.1"

from lakespec.plan.model import Column, JoinEdge, LogicalPlan, Metric, QualityRule, Table

__all__ = [
    "Column",
    "JoinEdge",
    "LogicalPlan",
    "Metric",
    "QualityRule",
    "Table",
    "__version__",
]

# Importing each adapter registers it. Keep these imports dependency-free:
# an adapter module must not import its engine at module scope, so that
# `lakespec adapters` works on a machine with nothing installed.
from lakespec.adapters import databricks, duckdb, postgres_pglake, spark_dbt  # noqa: F401
from lakespec.adapters.base import Adapter, Artifact, Capabilities, registry

__all__ = ["Adapter", "Artifact", "Capabilities", "registry"]

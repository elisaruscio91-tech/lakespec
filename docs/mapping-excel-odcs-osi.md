# Workbook → ODCS + OSI

The machine-readable version is [`schemas/workbook.mapping.yaml`](../schemas/workbook.mapping.yaml);
this page explains it.

## Why two standards, not one

They cover different layers of the pipeline and you need both.

| | ODCS | OSI / Apache Ossie |
|---|---|---|
| Layer | physical / contractual | semantic |
| Drives | **bronze → silver** | **silver → gold, and the agents** |
| Holds | types, keys, constraints, quality, transform lineage | metrics, dimensions, synonyms, instructions |

They share the join graph. That is derived once from the workbook and emitted
into both — which is where the no-drift property comes from.

## The five columns you probably already have

Most hand-written data models have these. Here is where each one lands.

| Workbook column | ODCS | OSI |
|---|---|---|
| field name | `properties[].name` (+ `physicalName` when they differ) | `datasets[].fields[].name` |
| type | `logicalType` **and** `physicalType` — ODCS separates them, and you want that: `logicalType: string` + `physicalType: varchar(18)` | `datatype` |
| description | `description`, plus `businessName` at table level | `description`, `label` |
| key | `primaryKey: true` + `primaryKeyPosition: 1`, plus `required`, `unique`. The position is what makes composite keys expressible — a boolean cannot | `primary_key: [...]`, `unique_keys` |
| relation | property level `relationships: [{to: customers.id, type: foreignKey}]`; table level with `from`/`to` lists for composite keys; cardinality in `customProperties` as `property: cardinality` | `relationships[]` with `name`, `from`, `to`, `from_columns`, `to_columns` |

## The columns worth adding, in order of value

### 1. `classification` and `critical`

`public` / `internal` / `restricted`, plus `criticalDataElement`.

This is the column that makes the agent safe: it is what stops a tax ID ending
up in a chart. Of everything in the workbook, this is the column to get right
first.

### 2. `source_objects`, `transform_sql`, `transform_note`

→ `transformSourceObjects`, `transformLogic`, `transformDescription`.

ODCS has native fields for *which source objects* a column comes from and *with
what logic*. That is the bronze → silver step as part of the contract instead of
buried in code — and it is what turns lakespec from a validator into a
generator.

### 3. `quality`

Column level and table level. A tiny expression vocabulary (`not null`,
`unique`, `> 0`, `between 0 100`, `rows > 1000`) so an analyst writes tests
without knowing they are writing tests. Anything richer goes straight into the
YAML.

### 4. `allowed_values` and `examples`

→ `enum` with `value`/`label` pairs, and `examples`. The decode tables, plus
sample values — which matter enormously for a natural-language layer picking the
right filter.

### 5. `synonyms`, `label`, and model-level `instructions`

→ OSI `ai_context`, which is a string or an object with `instructions`,
`synonyms` and `examples`. Here is where the business writes *fatturato =
revenue = ricavi*, and the agent stops being wrong.

### 6. `partition` and `is_time`

→ ODCS `partitioned` + `partitionKeyPosition`; OSI `dimension: {is_time: true}`.
Note OSI has no separate `dimensions` list — dimensionality sits on the field.

## Workbook layout

One sheet per table is not enough. Four kinds of sheet:

| Sheet | One row per | Filled in by |
|---|---|---|
| `_tables` | table — physical name, business name, grain, owner, layer, tags | engineering |
| `<table name>` | column — everything above | engineering, reviewed by the business |
| `_relationships` | composite foreign key (single-column keys live in the `relation` column) | engineering |
| `_metrics` | metric — name, SQL, description, synonyms, owner, effective date | **the business** |
| `_lakespec` | hidden; the commit this export came from | lakespec |

The `_metrics` sheet being the business's own is not a nicety. A metric with no
owner and no description is rejected by `lakespec validate`, because an
unattributed metric is how drift starts.

## The round-trip rule

**YAML in git is the truth. The workbook is a checkout.**

Export stamps the commit; import three-way merges against it and reports
conflicts rather than overwriting. The analyst sees what moved underneath them.

## A caution

The ODCS docs note that the companion JSON Schemas may contain bugs and that
where schema and written standard disagree, **the standard wins**. Validate
against the schema for IDE convenience; do not build hard assumptions on it in
the compiler.

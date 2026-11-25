# lakespec

**One contract. Pipelines, catalog and agent context fall out of it.**

lakespec compiles an [ODCS](https://bitol.io) data contract plus an
[OSI](https://ossie.apache.org) semantic model into
whatever your lakehouse actually runs — and into the governed context your AI
agents read. Apache-2.0, self-hosted, no account required.

```bash
pip install -e ".[duckdb,dev]"
lakespec compile examples/retail/semantics/sales.osi.yaml --adapter duckdb --out out/
```

That runs on a laptop in under a minute. No cluster, no cloud, no credentials.

---

## The problem

In a normal stack the *meaning* of your data lives in three places:

| Where | What it holds | What it drifts from |
|---|---|---|
| dbt / Spark models | the transformations | the documentation |
| a data catalog | the documentation | the code |
| nowhere | what an AI agent needs to answer correctly | everything |

They diverge the week after you write them. Then someone redefines "revenue" to
exclude VAT, no schema changes, and every dashboard quietly starts lying.

lakespec makes those three artefacts *outputs of one input*. There is nothing to
keep in sync because there is only one thing.

```
          ┌──────────────────────┐
          │  workbook (Excel)    │   the business edits here
          └──────────┬───────────┘
                     │  round-trip, git is the truth
          ┌──────────▼───────────┐
          │  ODCS + OSI in git   │   open standards, not our format
          └──────────┬───────────┘
                     │
          ┌──────────▼───────────┐
          │   logical plan       │   engine-neutral, no infrastructure
          └──────────┬───────────┘
      ┌──────────┬───┴──────┬──────────────┐
      ▼          ▼          ▼              ▼
   DuckDB   Spark/dbt   Postgres      Databricks        + agent context (MCP)
                        + pg_lake    + Unity Catalog
```

## What lakespec is not

- **Not a platform.** It is a compiler. It has no runtime, no scheduler, no UI,
  no storage. It emits files you run where you already run things.
- **Not a new format.** ODCS is a Linux Foundation standard rated *Adopt* on the
  Thoughtworks Technology Radar; OSI (now Apache Ossie, incubating) is at the Apache Foundation with Snowflake,
  dbt Labs, Salesforce, Google and Databricks in the working group. Inventing a
  format would be the fastest way to make this unadoptable.
- **Not a GUI pipeline builder.** A pipeline drawn with a mouse cannot be
  diffed, reviewed or tested. The spreadsheet here is an *editing surface*; the
  YAML in git is the truth.

## How it works

### 1. The contract carries more than a schema

ODCS already has fields for the things most teams keep in tribal memory:

```yaml
- name: net_amount
  logicalType: number
  physicalType: decimal(18,2)
  description: Importo netto IVA esclusa, al netto degli sconti riga.
  classification: internal          # governance
  criticalDataElement: true
  transformSourceObjects:           # lineage, as data
    - bronze.raw_orders
    - bronze.raw_order_discounts
  transformLogic: "raw_orders.gross_amount - coalesce(raw_order_discounts.amount, 0)"
  quality:
    - metric: nullValues
      mustBe: 0
```

`transformLogic` + `transformSourceObjects` are what make this a *generator*
rather than a validator: bronze → silver is emitted from the contract, so the
lineage is real instead of a diagram someone drew once.

### 2. The semantic model carries the meaning

OSI holds metrics, dimensions, join paths — and native AI context:

```yaml
metrics:
  - name: fatturato
    expression:
      dialects:
        - dialect: ANSI_SQL
          expression: "SUM(CASE WHEN status <> 'cancelled' THEN net_amount ELSE 0 END)"
    ai_context:
      synonyms: [revenue, ricavi, giro d'affari]
      instructions: >
        This is the only valid definition of revenue. Do not recompute it,
        do not sum net_amount directly.
```

### 3. The agent picks from a closed vocabulary. It does not write SQL.

This is the design decision that matters most.

`lakespec context` emits the vocabulary: tables, visible columns, metrics,
synonyms, declared join paths, instructions. A natural-language layer returns a
**semantic query** — metric, dimensions, filters, grain — and lakespec compiles
the SQL from the declared definitions.

Not caution for its own sake. Correctness:

- the join path comes from the contract, not from a guess
- the aggregation comes from the metric definition, so there is one answer
- fan-out double counting becomes detectable instead of silent
- the same question yields the same SQL, every time, auditably
- **because the choice set is closed, a small open-weights model is enough** —
  which is what makes a fully on-premise, no-data-leaves-the-building
  deployment possible at all

Columns marked `restricted` are withheld from that context by default. That is a
default, not a security boundary: enforcement belongs in the engine, via the
adapter. The `postgres_pglake` target can turn a classification into a real
enforced column privilege; most targets cannot, and say so.

### 4. Schema evolution is classified, not discovered in production

```console
$ lakespec diff v1/sales.osi.yaml v2/sales.osi.yaml
[semantic] metric fatturato: definition changed
    this is metric drift: the number moves while nothing in the schema does
    migration: major bump plus an effective-from date; keep the old definition available
[breaking] customers.segment: became required
    existing rows may hold nulls
    migration: backfill first, then tighten the contract
[backward] customers.segment: allowed values added: ['public_sector']

3 change(s), 2 requiring human ratification
suggested version: 1.0.0 -> 2.0.0
```

Four categories, three borrowed from schema registries and one that they do not
have:

| | Meaning | Bump |
|---|---|---|
| `backward` | new readers handle old data — nullable column, widened type, new enum value | minor |
| `forward` | old readers handle new data — something optional removed | major |
| `breaking` | structural break — drop, rename, narrow, key change | major |
| `semantic` | **name and type unchanged, meaning changed** | major |

The last one is the one that hurts, and nothing in a type system catches it.
See [docs/compatibility.md](docs/compatibility.md).

Upstream drift and intentional evolution are different problems and get
different machinery: bronze stays permissive and records the observed schema,
new columns land but stay **quarantined** until accepted into the contract, and
breaking changes fail fast rather than propagating silently.

### 5. Agents propose. Humans ratify.

An agent can read your documentation on SharePoint, Drive or Confluence and
draft contracts from it. It must never merge one.

The contract is what makes everything downstream trustworthy. If the contract is
itself probabilistic, you have moved the hallucination one layer up and given it
authority — and the whole proposition ("the agent knows `tax_id` is PII")
collapses, because an LLM guessed that classification.

So the work is split by what each party is actually good at:

| Step | Who | Why |
|---|---|---|
| profile the source — types, null rates, cardinality, candidate keys, FK candidates by value overlap | **deterministic code** | this is measurement, not inference |
| fill descriptions, labels, synonyms, instructions from documentation | LLM | this is prose |
| link each field to its `authoritativeDefinitions` entry with a deep link, confidence and quote | LLM | the job is *citing* meaning, not inventing it |
| `classification`, `primaryKey`, metric definitions | **human, always** | security and correctness consequences |

Documentation is stale and self-contradictory, so the flow is not
*document → contract*. It is **document + profiled reality → conflict report**:

> the data dictionary says `customer_id` is numeric; the actual column is
> `varchar` with 3% non-numeric values

That report is a deliverable on its own, before any of the rest of the platform
exists. Schema: [schemas/conflict-report.schema.json](schemas/conflict-report.schema.json).

One security note that belongs in a README rather than in someone's head: if an
agent ingests documents and the output is a governance artefact declaring what
is PII, that is a prompt-injection surface with legal consequences. Retrieved
documents are **data, never instructions**, and no classification change is ever
applied without a human signature. See [docs/agents.md](docs/agents.md).

## Targets

| Adapter | Status | Notes |
|---|---|---|
| `duckdb` | **working** | reference implementation; runs in CI with no infrastructure |
| `spark_dbt` | declared | dbt models + tests; shape documented in the module |
| `postgres_pglake` | declared | Postgres as Iceberg catalog; the only target that can *enforce* classifications |
| `databricks` | declared | registers semantics into Unity Catalog |

`lakespec adapters` prints what each one supports. An adapter that cannot carry
a plan feature says so loudly rather than emitting something that quietly means
less than your contract does:

```console
$ lakespec compile examples/retail/semantics/sales.osi.yaml --adapter duckdb --out out/
  warning: join edges are declared but this target cannot enforce them
  warning: restricted columns are declared but this target cannot tag them;
           enforcement must happen elsewhere
```

Writing a new adapter is days, not months — it is a pure function from logical
plan to text. That is the entire reason the plan sits in the middle, and
portability across targets is the property the whole design exists to protect.
**Never let the core take a dependency only one target can satisfy.**

## Commands

```
lakespec validate <model.osi.yaml>                      check model + contracts
lakespec plan     <model.osi.yaml>                      print the logical plan
lakespec compile  <model.osi.yaml> --adapter X --out Y   emit native artefacts
lakespec context  <model.osi.yaml>                      governed agent context, JSON
lakespec diff     <old> <new> [--strict]                classify changes
lakespec adapters                                       targets and capabilities
```

## Status

Pre-alpha, and deliberately **spec-first**. What exists is the specification, a
complete worked example, the compatibility taxonomy, the agent rules and the
adapter interface — the things worth arguing about before months go into code.

If you think the mapping is wrong, [say so](../../issues). That is what this
stage is for.

Roadmap: Excel round-trip → `spark_dbt` → MCP server → `postgres_pglake` →
`databricks` → semantic query compiler → ODPS data-product layer.

## Docs

- [docs/architecture.md](docs/architecture.md) — the three layers and why the boundaries sit there
- [docs/mapping-excel-odcs-osi.md](docs/mapping-excel-odcs-osi.md) — every workbook column to its standard key
- [docs/compatibility.md](docs/compatibility.md) — the change taxonomy as a decision table
- [docs/agents.md](docs/agents.md) — what an agent may and may not write
- [README.it.md](README.it.md) — in italiano

## License

Apache-2.0, matching ODCS and OSI. Your contracts stay yours and work outside
this tool — that is the point.

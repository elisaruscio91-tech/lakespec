# Ontology layer (design proposal)

**Status: proposal. Nothing here is implemented.** This page describes where I
want to take lakespec next and the questions I haven't answered yet.

## The idea

Today lakespec has two layers: ODCS (physical, contractual) and OSI (semantic).
Neither says what a business concept *is*. "Revenue", "active customer" and
"order" are defined in documents scattered across a company, and those
definitions drift the same way catalogs and pipelines do.

An ontology layer would sit above the contract and the semantic model:

- **concepts** (customer, order, revenue) with a definition and synonyms
- **relations** between concepts
- **links** from each concept to the ODCS fields and OSI metrics that implement it

Agents would choose from this vocabulary, the same way they already choose from
the closed vocabulary of metrics, dimensions and filters.

## Two tiers: declared and proposed

The central rule: **AI can propose meaning, only a person can declare it.**

| Tier | Written by | Lives in | Read by agents |
|---|---|---|---|
| `declared` | a person, or approved by one | YAML in git | yes, the only tier agents rely on |
| `proposed` | an extractor (AI or rule-based) | a separate file or directory, never merged automatically | no, until promoted |

Every `proposed` item carries its provenance:

- source (URI of the document, ticket or message)
- extractor name and version
- extraction date
- confidence
- the exact text it was derived from

Promotion from `proposed` to `declared` is a pull request. A reviewer sees the
source text next to the claim and decides. This keeps the history auditable and
stops an inference from silently changing what "revenue" means. It is the same
concern as the `semantic` compatibility category in
[compatibility.md](compatibility.md): the name stays, the meaning moves.

## Conflicts

`proposed` items that contradict `declared` ones are not discarded. They go in
the conflict report ([`schemas/conflict-report.schema.json`](../schemas/conflict-report.schema.json)),
next to the conflicts between documentation and profiled data. Examples:

- a Confluence page defines "active customer" as 90 days, the declared concept says 30
- the dictionary says a column is numeric, the profiled data has 3% non-numeric values

This is the most useful output of the layer, and it can be used without the
rest of lakespec.

## Sources

lakespec should not build connectors to every tool. The proposal is a thin
interface:

```
Source.fetch() -> iterable of Evidence
Evidence = { text, uri, author, modified, permissions }
```

Concrete sources (a local folder, Drive, SharePoint, Jira, Slack) should come
from existing MCP servers or plugins, outside the core. The first one should be
a local folder of documents, so everything runs on a laptop.

Extraction must work with a small open-weights model running locally. If it
needs a hosted frontier model, the on-premise story breaks.

## Governance

This is the hardest part and should be designed before any connector.

- A document the reader cannot access must not produce a `proposed` item that
  they can see. Permissions in `Evidence` have to survive extraction.
- `classification` (`public` / `internal` / `restricted`) should propagate from
  the source to the proposed item, with the strictest value winning.
- Restricted evidence should never leave the machine it was read on, including
  to a hosted extractor.

I don't yet know how to do this correctly across sources with different
permission models. I would rather say so than hide it.

## What this is not

lakespec does not try to be an agent platform, a lakehouse, an ingestion
engine or an app builder. The ontology is a layer other systems can read. The
MCP server (see [agents.md](agents.md)) is how multiple agents share the same
context instead of copying each other's outputs.

## Open questions

1. **Format.** I don't want to invent one. SKOS, the ODCS glossary, OSI
   `ai_context` and OWL each cover part of this. Which one, or which
   combination, fits best?
2. **Granularity.** Concept-level only, or also rules ("an order is active
   until it ships")?
3. **Confidence.** Is a single number meaningful, or should evidence count and
   source authority be kept apart?
4. **Staleness.** When a source document changes, what happens to the
   `declared` items that were promoted from it?
5. **Order of work.** The roadmap already has the Excel round-trip, the MCP
   server and the semantic query compiler. The ontology should probably follow
   the compiler.

## Smallest useful version

1. a schema for `declared` concepts, linked to ODCS fields and OSI metrics
2. one `Source`: a local folder of Markdown or text files
3. an extractor that runs with a local model and writes `proposed` items
4. a promotion flow through pull requests
5. contradictions between `proposed` and `declared` reported as conflicts

That runs on a laptop with DuckDB and no cloud.

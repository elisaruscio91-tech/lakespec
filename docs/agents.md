# Agents

## The rule

**An agent proposes. A human ratifies. The output of an agent is a pull request,
never a contract in production.**

Not generic caution. The contract is the single thing that makes everything
downstream trustworthy. If the contract is itself probabilistic, the
hallucination has moved one layer up and been given authority — and the whole
proposition of this project, that the agent *knows* `tax_id` is PII, collapses
because a model guessed it.

## Division of labour

| Work | Performed by | Why |
|---|---|---|
| types, null rates, cardinality, candidate keys, FK candidates by value overlap | deterministic profiling | measurement, not inference |
| `description`, `businessName`, `label`, `ai_context.synonyms`, `instructions` | LLM | prose, cheap to verify |
| `authoritativeDefinitions` links with deep link, confidence, quote | LLM | the job is *citing* meaning, not inventing it |
| `classification`, `criticalDataElement` | **human only** | a disclosure decision |
| `primaryKey`, metric expressions, declared grain | **human only** | wrong here means every number is wrong |

Every agent-filled field carries provenance. ODCS `authoritativeDefinitions`
exists for exactly this, so the agent's task becomes *linking a field to its
authoritative definition* rather than authoring a meaning. A human can check
that in ten seconds, which is the difference between a reviewable proposal and a
plausible guess.

## Natural-language surfaces, ordered by risk

Ship in this order. Each one is useful alone.

1. **Read and debug.** *"Why did the orders pipeline fail last night?"* Reads
   contract, schema diff, quality results, lineage. Read-only, no authority over
   anything, and roughly 70% of the value a manager perceives. Ship first.
2. **Explain a diff.** *"What breaks if I accept this?"* Impacted downstream
   consumers, compatibility class, proposed migration.
3. **Propose a change.** *"Add shipping country from the CRM."* Emits the YAML
   diff, the classification and the migration plan, as a PR. A human merges.

A contract change applied autonomously by an agent: never. In regulated
settings this is often a hard requirement rather than a preference: no
governance change without a human signature.

## Query answering

The agent does not write SQL. `lakespec context` gives it a closed vocabulary;
it returns a semantic query — metric, dimensions, filters, grain — and the
compiler generates SQL from the declared definitions. See the README section and
`mcp/context.py`.

Consequence worth stating plainly: a closed choice set means a small
open-weights model is sufficient, so the whole natural-language layer can run
on-premise with no data leaving the building.

## Prompt injection

An agent that ingests documents from SharePoint, Drive or Confluence and emits a
governance artefact declaring what is PII is a prompt-injection surface with
legal consequences. A sentence in a Word file must never be able to reclassify a
column.

- Retrieved document content is **data, never instruction**.
- Classification changes require a human signature, always.
- Metadata is sanitised before it reaches a model's context.
- The conflict report records what was claimed, by whom, with what confidence —
  so a suspicious claim is visible rather than absorbed.

Carry this into your deployment docs as well: it is an operational
requirement, not a disclaimer.

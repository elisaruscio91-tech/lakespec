# Change compatibility

A decision table, so "is this safe to merge?" has a repeatable answer instead of
a conversation.

## Two different problems

| | Upstream drift | Intentional evolution |
|---|---|---|
| What happened | the source changed without telling you | the business wants something new |
| Nature | a **detection** problem | a **change management** problem |
| Machinery | profile every batch, reconcile against the contract | diff, classify, ratify, version |

Most tools conflate these. They need opposite handling, so lakespec keeps them
apart.

## The taxonomy

Three categories are borrowed from Avro and Protobuf schema registries, because
that world settled this fifteen years ago and data teams already know the words.
The fourth is the one registries do not have.

| Category | Definition | Examples | Bump |
|---|---|---|---|
| `backward` | new readers handle old data | nullable column added; `integer`→`number`; `date`→`timestamp`; enum value added | minor |
| `forward` | old readers handle new data | optional column removed; `required` relaxed | major |
| `breaking` | structural break | column dropped or renamed; type narrowed; primary key changed; enum value removed; `required` tightened; join path removed | major |
| `semantic` | **structure identical, meaning changed** | metric expression changed; `transformLogic` changed; declared grain changed; `restricted` loosened to `public` | major |

### Why `semantic` has to be its own category

Someone redefines revenue to exclude VAT. Nothing in the schema moves. Every
type check passes. Every dashboard quietly starts lying, and you find out in a
board meeting.

Treating this as first-class is the most useful thing the module does. A change
to a metric expression is a major bump, and it carries a migration note.

## Physical mechanics

Iceberg does schema evolution by column ID, so add, drop, rename and reorder do
not rewrite data. The physical layer is not the problem. **Semantic propagation
downstream is.**

## The pipeline rules

1. **Bronze is permissive.** Never reject raw data. Land it all and record the
   observed schema per batch as metadata.
2. **Reconcile.** Compare observed schema against the contract and emit a
   classified diff.
3. **Quarantine, don't propagate.** A new column lands in bronze and does *not*
   reach silver until someone accepts it into the contract. This is the safety
   property that makes step 1 safe.
4. **Fail fast on breaking.** Never in silence.
5. **Expand/contract for breaking changes.** Add the new alongside the old,
   compute both, migrate consumers, then remove. ODCS carries contract `version`
   and `status`; per-property end-of-life goes in `customProperties` so the
   compiler knows when to stop emitting the old branch.
6. **Metrics are versioned with an effective date.** A redefinition keeps the old
   definition available for historical comparison.

## The workbook merge problem

The analyst edits the spreadsheet while the contract upstream moves. Now you
have a merge conflict in a binary file.

Every exported workbook carries the commit it came from in a hidden `_lakespec`
sheet. On import, if HEAD has moved, lakespec performs a three-way merge against
that base and reports conflicts. Never a silent overwrite.

**The YAML in git is the truth. The workbook is a checkout.** A spreadsheet
cannot be diffed or code-reviewed, which is exactly why it must not be the
source of truth — and exactly why it is still the right editing surface for
someone who will never open a terminal.

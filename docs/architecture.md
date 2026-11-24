# Architecture

Three layers, and the boundaries between them are load-bearing.

## Layer 1 — the spec

ODCS contracts and OSI semantic models, as YAML, in git. No dependencies, no
code, pure data. Readable by anything, including tools that have never heard of
lakespec.

**The boundary:** nothing in this layer knows lakespec exists. We extend the
standards only through the extension points they provide — ODCS
`customProperties`, OSI `custom_extensions` — never by forking a key.

## Layer 2 — the core

`spec/` loads, `plan/` folds both documents into one **logical plan**: tables,
columns, the join graph, transforms, quality rules, metrics.

**The boundary:** `plan/model.py` must never import an engine, a driver or a
cloud SDK. If you reach for one, the abstraction has leaked and the same
contract no longer compiles everywhere.

The plan is also where the no-drift property is actually earned: the join graph
and the column meanings are read once and handed to every emitter, so pipelines,
catalog entries and agent context cannot disagree.

## Layer 3 — the adapters

A pure function from logical plan to native text artefacts. No execution; the
host runs things.

**The boundary:** an adapter reads the plan, never the YAML. If it needs a field
the plan does not carry, add it to the plan.

Each adapter declares `Capabilities`. `lakespec compile` warns for every plan
feature the target cannot express. An adapter that silently drops quality rules
is worse than one that refuses, because the contract then promises something
nobody is checking.

## Why DuckDB is the reference, not the afterthought

It is the adapter that decides whether the project is adoptable. The first
experience has to be a laptop, a `pip install` and one command — no cluster, no
cloud account, no credentials. A project whose first step requires
infrastructure gets tried by almost nobody.

It is also how the compiler is tested in CI with no infrastructure at all.

## Where state lives

Nowhere in lakespec. Contracts live in git, data lives in the customer's own
storage, credentials never touch this tool. The only durable artefact lakespec
produces is text you can read in a pull request.

## The one decision to re-litigate before 1.0

The semantic query compiler — NL → semantic query → SQL — currently exists only
as the protocol described in `mcp/context.py`. Compiling a model-scoped metric
(one that spans datasets) requires emitting the FROM/JOIN clause from
`plan.joins`, including fan-out detection so adding a dimension from a
one-to-many side does not silently double a sum. That is the hard part of this
project and the part most worth getting right slowly.

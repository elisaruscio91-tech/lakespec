# Contributing

Pre-alpha and spec-first. The most valuable contribution right now is not code —
it is telling us the mapping is wrong.

## What helps most

1. **Argue with [the mapping](docs/mapping-excel-odcs-osi.md).** If a field in
   your data model has no home in ODCS or OSI, open an issue. That gap is either
   a mapping bug or something to take upstream to Bitol or Apache Ossie.
2. **Bring a real data model.** An anonymised workbook from a real project is
   worth more than any amount of speculation about what people write down.
3. **Write an adapter.** The logical plan is stable. Each unimplemented adapter
   module documents its target shape in the docstring.

## Rules that are not negotiable

- **No new format.** Extend ODCS and OSI only through `customProperties` and
  `custom_extensions`. A forked key makes this project an orphan.
- **The core imports no engine.** `plan/model.py` must stay free of drivers,
  engines and cloud SDKs. One leaked dependency and the same contract no longer
  compiles everywhere, which is the one property this design cannot lose.
- **Adapters emit, they do not execute.** `emit()` has no side effects.
- **Declare your gaps.** An adapter that silently drops quality rules is worse
  than one that refuses.
- **No agent writes a classification.** See [docs/agents.md](docs/agents.md).
- **Tests run with no infrastructure.** If it needs a cluster, nobody runs it.

## Setup

```bash
pip install -e ".[duckdb,workbook,dev]"
pytest -q
ruff check .
```

## License

Apache-2.0, matching ODCS and OSI. By contributing you agree your work ships
under it.

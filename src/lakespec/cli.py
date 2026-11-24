"""lakespec command line.

    lakespec validate   <model.osi.yaml>
    lakespec plan       <model.osi.yaml>
    lakespec compile    <model.osi.yaml> --adapter duckdb --out out/
    lakespec context    <model.osi.yaml>
    lakespec diff       <old.osi.yaml> <new.osi.yaml>
    lakespec adapters
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lakespec import __version__
from lakespec.adapters import registry
from lakespec.compat import classify_changes, next_version
from lakespec.mcp.context import to_json
from lakespec.plan import build_plan
from lakespec.spec import SpecError, load_bundle


def _plan(path: str):
    return build_plan(load_bundle(path))


def cmd_validate(args: argparse.Namespace) -> int:
    plan = _plan(args.model)
    problems: list[str] = []

    for table in plan.tables:
        if not table.primary_key:
            problems.append(f"{table.name}: no primary key declared, so grain is unverifiable")
        if not table.source:
            problems.append(f"{table.name}: no OSI source, the semantic model cannot be queried")
        for col in table.columns:
            if col.classification is None:
                problems.append(f"{table.name}.{col.name}: no classification; default to internal explicitly")
    for metric in plan.metrics:
        if not metric.sql:
            problems.append(f"metric {metric.name}: no expression for the requested dialect")
        if not metric.description:
            problems.append(f"metric {metric.name}: no description, so an agent cannot pick it reliably")

    print(f"{plan.name}: {len(plan.tables)} tables, {len(plan.metrics)} metrics, {len(plan.joins)} join paths")
    for problem in problems:
        print(f"  warning: {problem}")
    print("ok" if not problems else f"{len(problems)} warning(s)")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    plan = _plan(args.model)
    print(f"plan: {plan.name}")
    for table in plan.tables:
        pk = ", ".join(c.name for c in table.primary_key) or "-"
        print(f"  {table.name}  layer={table.layer or '-'}  pk=({pk})  columns={len(table.columns)}")
        for col in table.columns:
            flags = []
            if col.is_primary_key:
                flags.append("pk")
            if col.required:
                flags.append("required")
            if col.classification:
                flags.append(col.classification)
            if col.transform:
                flags.append("derived")
            if col.is_time:
                flags.append("time")
            print(f"      {col.name}: {col.logical_type} [{', '.join(flags) or '-'}]")
    for join in plan.joins:
        print(f"  join {join.from_table} -> {join.to_table} on {join.from_columns}={join.to_columns} ({join.cardinality or 'cardinality unknown'})")
    for metric in plan.metrics:
        print(f"  metric {metric.name} ({metric.dataset or 'model-scoped'})")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    plan = _plan(args.model)
    adapter = registry.get(args.adapter)

    for gap in adapter.unsupported(plan):
        print(f"  warning: {gap}", file=sys.stderr)
    for note in adapter.capabilities.notes:
        print(f"  note: {note}", file=sys.stderr)

    written = adapter.write(plan, args.out)
    for path in written:
        print(path)
    print(f"{len(written)} file(s) written to {args.out} via the {adapter.name} adapter")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    plan = _plan(args.model)
    output = to_json(plan, include_restricted=args.include_restricted)
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(args.out)
    else:
        print(output)
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    old, new = _plan(args.old), _plan(args.new)
    changes = classify_changes(old, new)
    if not changes:
        print("no changes")
        return 0
    for change in changes:
        print(change)
        if change.detail:
            print(f"    {change.detail}")
        if change.migration:
            print(f"    migration: {change.migration}")
    blocking = [c for c in changes if c.blocking]
    current = next((t.contract_version for t in old.tables if t.contract_version), "0.0.0")
    print(f"\n{len(changes)} change(s), {len(blocking)} requiring human ratification")
    print(f"suggested version: {current} -> {next_version(current, changes)}")
    return 1 if blocking and args.strict else 0


def cmd_adapters(args: argparse.Namespace) -> int:
    for name in registry.names():
        adapter = registry.get(name)
        caps = adapter.capabilities
        supported = [k for k, v in vars(caps).items() if v is True]
        print(f"{name}: {', '.join(supported) or 'nothing declared'}")
        for note in caps.notes:
            print(f"    {note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lakespec", description=__doc__)
    parser.add_argument("--version", action="version", version=f"lakespec {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check a model and its contracts")
    p.add_argument("model")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("plan", help="print the logical plan")
    p.add_argument("model")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("compile", help="emit native artefacts for a target")
    p.add_argument("model")
    p.add_argument("--adapter", default="duckdb", choices=registry.names())
    p.add_argument("--out", default="out")
    p.set_defaults(func=cmd_compile)

    p = sub.add_parser("context", help="emit the governed agent context as JSON")
    p.add_argument("model")
    p.add_argument("--out")
    p.add_argument(
        "--include-restricted",
        action="store_true",
        help="include restricted columns; refuse this in any shared deployment",
    )
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("diff", help="classify the changes between two models")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("--strict", action="store_true", help="exit non-zero on a breaking change")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("adapters", help="list targets and what each supports")
    p.set_defaults(func=cmd_adapters)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except NotImplementedError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

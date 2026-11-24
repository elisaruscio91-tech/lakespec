"""Excel <-> YAML round-trip.

Not implemented yet. The column mapping is already fixed and machine readable in
`schemas/workbook.mapping.yaml`, which is deliberately the first thing that
exists: the mapping is the contract between the business and the repo, and it
deserves review before any code reads it.

The rule that must survive implementation, because everything else depends on it:

    The YAML in git is the source of truth. The workbook is a checkout.

So every exported workbook carries the commit it came from, and import performs a
three-way merge against that base. If HEAD has moved, the analyst is shown what
changed underneath them -- never a silent overwrite. A spreadsheet cannot be
diffed or reviewed; that is precisely why it must not be the truth.
"""

from __future__ import annotations

__all__: list[str] = []

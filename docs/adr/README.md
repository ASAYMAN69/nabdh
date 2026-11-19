# Architecture Decision Records

This directory records decisions that change clinical behaviour, data contracts, or public
interfaces. Each ADR is immutable once accepted; superseding decisions get a new number.

There is no git repository in this workspace, so these records (together with SHA-256 hashes in
the change record) are the audit trail.

## Index

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-canonical-sex-encoding.md) | Canonical sex encoding and `sex_convention` contract | superseded by ADR-0002 | 2026-11-19 |
| [0002](0002-auto-detect-sex-encoding.md) | Auto-detect sex encoding from the uploaded column | accepted | 2026-11-19 |

## Conventions

- Number sequentially: `NNNN-short-slug.md`.
- Status is one of `proposed`, `accepted`, `deprecated`, `superseded by ADR-NNNN`.
- Keep the decision and its consequences in the same file; do not rewrite history after acceptance.
- Link the ADR from the code or docs it governs.
- Use [template.md](template.md) as the starting point.

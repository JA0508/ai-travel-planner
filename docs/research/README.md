# Research Snapshots

This directory contains dated human-facing product research snapshots.

## Current snapshot

- `AI旅行规划产品深度研究_竞品UI与功能蓝图_2026-07-12.docx`

This file is a **2026-07-12 snapshot** for competitor research, UI pattern
analysis, and long-range product roadmap reference.

It is not the current implementation truth.

## Authority boundary

Research snapshots must not override:

- current code
- schemas
- tests
- ADRs
- `docs/product/CURRENT_PHASE.md`
- `docs/product/PRODUCT_DIRECTION.md`

Use research documents as context for product thinking, not as direct
implementation contracts.

Before implementing any feature referenced by a research snapshot, Codex must
re-audit the real repository code, schemas, services, API contracts, frontend
state owners, tests, and current phase documentation.

## Known staleness

The research snapshot may include historical repository observations, old file
sizes, old missing-capability lists, or roadmap sequencing that reflected the
project on 2026-07-12. Those statements must be treated as dated context unless
they are confirmed against current `main`.

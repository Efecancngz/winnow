# Winnow

Predictive test selection: given a PR diff, pick and prioritize the tests
that actually need to run (coverage-based safety net + ML risk scoring).
Portfolio/learning project — see [docs/analiz.md](docs/analiz.md) §4 for why
this was built from scratch rather than using a closed-source tool.

Full design rationale: [docs/superpowers/specs/2026-08-21-winnow-design.md](docs/superpowers/specs/2026-08-21-winnow-design.md).
Current architecture: [docs/architecture.md](docs/architecture.md).
Handoff state: [HANDOFF.md](HANDOFF.md).

## Architecture (why, briefly)

Monolith-first, layered package: `ingest → store → selection → action`.
Outer layers depend on inner ones, never the reverse — `selection/` knows
nothing about GitHub, so the core algorithm is usable from a CLI or another
CI system. Patterns: Adapter (report parsers), Repository (SQLite access),
Strategy (swappable risk scorer). Full rationale in `docs/architecture.md`.

## Safety invariant

The deterministic coverage-based "must-run" set is never narrowed by the ML
layer — ML only adds/reorders. Missing or uncertain coverage data always
falls back to the full suite, visibly (never a silent skip). Any change that
touches `selection/pipeline.py` must preserve this.

## Run commands

Not applicable yet — implementation not started (see HANDOFF.md).

## Config

`WINNOW_DB_PATH`, `WINNOW_COVERAGE_FORMAT`, `WINNOW_RISK_THRESHOLD`,
`WINNOW_MODE` — see `.env.example`.

## Standards

Follows the shared project standards: `Yazılım Projesi Standartları.md` in
the Obsidian vault (`06_Metadata/Reference/`). Notably: Conventional Commits
in English, no AI co-author trailers, MIT license, monolith-first default.

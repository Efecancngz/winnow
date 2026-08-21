# Winnow — Design Spec

**Date:** 2026-08-21
**Status:** Approved, pre-implementation

## Problem

Full CI test suites get slower as they grow, even though most code changes only
affect a small fraction of the suite. Teams either accept the slow feedback
loop or buy a closed-source predictive test selection product (Launchable).
Winnow is an independent, open implementation of the technique described in
Google's Test Impact Analysis and Meta's 2019 "Predictive Test Selection"
research: given a PR diff, predict and prioritize which tests need to run.

## Requirements

**Functional**
- Given a git diff, extract affected tests from a historical coverage map.
- Score every test's failure risk from features: churn, historical failure
  rate, co-change frequency.
- Merge the deterministic "must-run" set with the ML-ranked set into a final,
  prioritized test list.
- Parse Cobertura XML and JUnit XML into a normalized internal model.
- Generate synthetic commit histories with known, injected failures (ground
  truth) to validate the selector before touching real data.
- Replay historical PRs from a real open-source repo and report
  precision/recall/estimated time saved (backtesting).
- Run as a GitHub Action that comments the selected test list on a PR.

**Non-functional**
- Recall-safe: missing/uncertain coverage data must never silently skip a
  test — fall back to running the full suite.
- Single-repo scale (hundreds to a few thousand tests); no distributed/
  multi-repo scope.
- Selection computation must run in seconds, not minutes.
- No dependency on paid/closed-source services.
- Language-agnostic core: any toolchain that emits Cobertura or JUnit XML
  can use it.

**Business**
- Purpose: portfolio and learning — demonstrate a technique rarely
  implemented end-to-end at student level.
- Audience: technical interviewers, GitHub visitors.
- Success criterion: a measurable result on a real open-source repo (e.g.
  "60% fewer tests run, 95% of real failures still caught") plus a working
  GitHub Action demo.

## Build vs. buy

Researched: Launchable (closed-source SaaS, no insight into the algorithm —
defeats the learning purpose), `pytest-testmon` (open source but pure
coverage-diff, no ML layer, Python/pytest-only), Google's TIA and Meta's 2019
predictive-test-selection paper (methodology published, no code released).

No open-source, language-agnostic tool combining a coverage safety net with
ML risk scoring was found. This justifies building it as a deliberate
learning project (§0.4 exception) — the goal is to understand the technique,
not just consume it. Solved sub-problems (XML parsing, git diffing, the ML
model itself) still use existing libraries; only the hybrid selection
algorithm and orchestration are original.

## Architecture

See [docs/architecture.md](../../architecture.md) for the full module
breakdown, diagrams, and pattern rationale. Summary: monolith-first, layered
package (`ingest` → `store` → `selection` → `action`), Adapter pattern for
report parsers, Repository pattern for the SQLite store, Strategy pattern for
swappable risk-scoring models.

## Tech stack

See [docs/architecture.md](../../architecture.md#tech-stack-decision-log) for
the full alternatives-considered table. Summary: Python 3.12, SQLite,
GitPython, `coverage.py` + Cobertura XML, `junitparser`, scikit-learn,
GitHub Actions.

## API contract

See [docs/api-spec.md](../../api-spec.md) for the GitHub Action input/output
contract and PR comment format.

## Testing strategy

- Unit tests for each parser against fixture reports.
- Simulation-based validation: injected synthetic failures must be reliably
  selected (recall is the critical safety metric here).
- Backtesting harness against the chosen open-source repo's historical PRs —
  this produces the headline portfolio metric.

## Open questions for implementation planning

- Which specific open-source repo to backtest against (to be chosen when
  wiring up the real-data phase).
- Exact feature set for the risk scorer (start minimal, expand only if
  backtesting shows it helps).

# Winnow

Predicts which tests actually need to run for a given code change, so CI
doesn't waste time re-running an entire suite on every PR.

## Why

Full-suite CI runs get slower as a suite grows, even though most changes
only touch a small fraction of it. Winnow combines a coverage-based safety
net with a lightweight ML risk model to select — and prioritize — the tests
that matter for a specific diff, independently implementing the technique
described in Google's Test Impact Analysis and Meta's 2019 "Predictive Test
Selection" research (no open-source, language-agnostic equivalent exists —
see [docs/analiz.md](docs/analiz.md) §4 for the full build-vs-buy check).

## Stack

Python · scikit-learn · SQLite · coverage.py · junitparser · GitPython · GitHub Actions

## Quick start

```bash
git clone <repo-url>
cp .env.example .env
pip install -e ".[dev]"
pytest
```

## Documentation

- [Analysis](docs/analiz.md) — problem, requirements, build-vs-buy
- [Architecture](docs/architecture.md) — modules, diagrams, tech decisions
- [API spec](docs/api-spec.md) — GitHub Action contract

## Status

Core engine (ingest, store, selection pipeline, synthetic bootstrap
validation) implemented and tested — 30+ tests passing. ML risk scoring,
real-repo backtesting, and the GitHub Action are a follow-up plan (see
[HANDOFF.md](HANDOFF.md)).

## License

MIT — see [LICENSE](LICENSE)

# Selection Unit — Design Spec

**Date:** 2026-09-10
**Status:** Approved, pre-implementation
**Scope:** Second of four follow-up sub-systems (collection → **selection unit** →
mutation-based ground truth → ML risk scorer → GitHub Action). This spec changes what
Winnow selects and scores. It does not touch the ML model or the mutation harness.

## Problem

Coverage is stored once per *test case*, but Jest only ever produces it per *test file*.
`collect_history` loops over the JUnit outcomes of a file and writes the same
`CoverageReport` once per case:

```python
for outcome in outcomes:
    coverage_repo.add_coverage(sha, outcome.test_id, coverage_report)
```

On mobx that is ~24 identical copies per file: **22.8 MB/commit against a necessary
~0.9 MB, a ~26× inflation.**

Disk is the symptom. The defect is that the schema asserts a per-case attribution that
was never collected. Every case in a file resolves to byte-identical coverage, so the
selector cannot distinguish two cases in the same file and never could — while the column
name `test_id` claims it can.

## The decision

**Winnow's selection unit is the test file.**

`test_id` stops being the selection key. `test_file` becomes it, everywhere selection
touches: `must_run_tests` → `SelectionPipeline` → `RiskScorer` → `failure_rate`.
Case-level rows survive in `test_outcomes` only, as diagnostics and as the raw material
the file-level failure rate aggregates from.

### Why: the cost unit, not the storage

The deciding measurement is from the mobx collection run: `api.js` (2 tests) and
`observables.js` (88 tests) both cost ~17–19 s. Per-file cost is independent of the
number of cases in the file, because the cost is Jest's per-file startup.

**Under Jest the atom of CI cost is the test file.** Selecting 3 of 88 cases in
`observables.js` saves nothing — the ~17 s is paid in full. A selection unit finer than
the cost unit cannot produce savings, by construction. Even if per-case attribution were
free and perfect, case-granular selection would measure zero CI improvement.

The 26× storage reduction is a consequence of this decision, not its justification. Read
back later, this must not be mistaken for a storage optimization.

### Two axes, not one

The 2026-09-08 session decided *source-side* granularity. This spec decides the *test
side*. They are independent, and the chosen combination is line × file.

| Axis | Question | Decision |
|---|---|---|
| Source side | Match a diff on the whole file, or on changed lines? | **Line level** (2026-09-08: file level is dead in mobx — all 54 source files are covered by all 11 sampled tests) |
| Test side | Is the selected and scored unit a case or a file? | **Test file** (this spec) |

### Alternatives rejected

**Collect real per-case attribution.** Run Jest once per case
(`--runTestsByPath <file> -t "<name>"`). Cost from measured numbers: ~775 cases/commit ×
17.4 s ≈ **3.7 h/commit** against the measured 8.8 min steady-state (~25×); the 30-commit run goes from one
night to roughly five days. It would also still be partly false: `-t` filters execution
but the whole module is still loaded and evaluated, so every case inherits the file's
import-time coverage — fabricated at exactly the boundary that matters.

**Normalize storage, keep the case identity.** Store coverage once per
`(commit, test_file)` and add a case→file join table. Removes the 26× duplication with no
downstream interface change — and preserves the epistemic duplication untouched. Every
case in a file still resolves to identical coverage. Same false claim, larger schema.

## Design

### Identity and path coordinates

`test_file` is a **repo-root-relative POSIX path**, e.g.
`packages/mobx/__tests__/v5/base/observables.js`.

The database already holds two path vocabularies that must agree: Cobertura's `file_path`
(repo-relative, normalized to `/`) and git diff paths (repo-relative, always POSIX).
Jest's `--listTests` emits **absolute host-separator** paths, so the collector must
normalize before storing.

This is the same failure shape as the Cobertura backslash defect: a mismatch raises
nothing, it just makes every lookup miss, and a selector that matches nothing falls back
to the full suite and reports success. One coordinate system for the whole database,
asserted by a test with a Windows-style input.

### Schema

```sql
CREATE TABLE test_coverage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_file TEXT NOT NULL,
    file_path TEXT NOT NULL,
    covered_lines TEXT NOT NULL,
    UNIQUE (commit_sha, test_file, file_path)
);

CREATE TABLE test_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_sha TEXT NOT NULL REFERENCES commits(sha),
    test_file TEXT NOT NULL,
    case_id TEXT NOT NULL,
    passed INTEGER NOT NULL,
    duration_seconds REAL NOT NULL
);

CREATE INDEX idx_test_coverage_file_path ON test_coverage (file_path);
CREATE INDEX idx_test_outcomes_test_file ON test_outcomes (test_file);
```

The `UNIQUE` constraint is the substantive part, not the rename. "Coverage is per test
file" is currently a fact upheld by discipline in one loop; as a constraint, a regression
becomes an `IntegrityError` on the first insert instead of a silent 26× return of the
original bug.

The case column is named `case_id`, not `test_id`. `test_id` means "the key selection runs
on"; after this change that is `test_file`. Leaving the old name on a different concept
reproduces the ambiguity that caused this defect.

Both tables are unindexed today; coverage reaches ~52k rows at 30 commits. Index usage is
to be confirmed with `EXPLAIN QUERY PLAN`. **No speedup figure is to be quoted unless
measured.**

**No migration.** `data/*/` is gitignored and holds 3 mobx commits. Re-collecting costs
~34 min and produces data in the new shape with no migration code to write or test.

### Collector

```python
rel = relative_posix(clone_dest, test_file)
coverage_repo.add_coverage(sha, rel, coverage_report)   # once per file
outcome_repo.add_outcomes(sha, rel, outcomes)
```

The per-outcome loop around `add_coverage` is removed.

A correctness fix falls out: a test file whose cases are all skipped yields an empty
`outcomes` list, so today the loop never executes and **that file's coverage is silently
dropped**. After the change coverage is written regardless of case count.

### Selection and scoring

- `CoverageRepository.tests_covering_file` → `test_files_covering(file_path, changed_lines)`.
  The line-level intersection and the "no line overlap → return every test for that file"
  fallback are unchanged.
- `SelectionResult.must_run`, `RankedTest`, `RiskScorer.score`, `all_test_ids` →
  `all_test_files`: all keyed on `test_file`.
- `TestOutcomeRepository.failure_rate(test_file)` becomes an aggregation.

**Definition of the file-level failure rate:** the fraction of commits in which this file
had **at least one failing case**.

The rejected alternative is the fraction of all case-runs that failed. Under it,
`observables.js` with one permanently broken case out of 88 scores 0.011 —
indistinguishable from a healthy file. The scorer's question is "is it worth running this
file", so the matching label is "did running this file surface a failure".

### Data hygiene: permanently failing cases

Three mobx tests fail in every collected commit (they need a production build that
`--selectProjects mobx` does not run). Their variance is zero and they are worthless as
labels. Unexcluded, they pin three whole test files at `failure_rate` 1.0 under the
definition above, and the heuristic scorer selects those files on every diff forever.

Exclusion is applied **before** the roll-up, at aggregation time.

Rule: a case is permanently failing if it has **≥ N observations and has never passed.**

The minimum-observation guard is mandatory, not defensive padding: at 3 collected commits
every case looks constant. This is the same shape as the Phase 2 circuit breaker — an
error *rate* over a minimum sample, never "N consecutive". N is configuration with a
documented default, to be re-examined against the 30-commit run rather than fixed now.

### Out of scope

- Source-side line-level matching: decided, unchanged.
- Mutation ground truth: unaffected and compatible. Stryker's `killedBy` is per case; a
  mutant counts as caught if any case in the file kills it — the same roll-up as the
  failure rate. Recording per case and rolling up keeps the coupling-hypothesis question
  answerable.
- ML feature engineering.

## Testing

Test-first throughout. The tests that carry the design:

1. A file with 40 cases writes coverage rows for the files it covers — not 40× that.
2. The `UNIQUE` constraint rejects a duplicate `(commit_sha, test_file, file_path)`.
3. A Windows absolute path from `--listTests` normalizes to repo-relative POSIX.
4. A test file with zero cases still stores its coverage.
5. `failure_rate` under the at-least-one-failing-case definition, across several commits.
6. The hygiene guard both fires at ≥ N observations and does **not** fire below N.
7. Line-level selection returns the expected test files (the existing pipeline tests,
   re-expressed in the new identity).

**Verification on real data, not only pytest:** re-collect the 3 mobx commits, confirm
~0.9 MB/commit, and confirm that line-level selection returns the same test files as
before the change once rolled up. If selection output shifts, the refactor lost
information, and that should surface as a diff rather than a hunch.

## Risks

`simulate/generator.py` and `tests/test_bootstrap_validation.py` speak the old identity,
and they *define* the synthetic world the engine was validated against. Mechanically
renamed, they would keep passing while validating a world that no longer exists. They
must generate coverage per test file with several cases per file, or the bootstrap
validation is theatre.

Secondary: the re-collection is the first chance to confirm the ~0.9 MB/commit figure.
It is derived from the 26× ratio, not yet observed.

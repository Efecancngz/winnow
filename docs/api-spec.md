# API Spec — GitHub Action Contract

Build vs. buy: coverage/test report formats (Cobertura XML, JUnit XML) are
established industry standards consumed as-is — nothing here is invented.
The only original contract is the Action's own inputs/outputs, drafted below
before implementation.

## `action.yml` (draft)

```yaml
name: 'Winnow — Predictive Test Selection'
description: 'Selects and prioritizes the tests that matter for this PR diff.'
inputs:
  db-path:
    description: 'Path to the Winnow SQLite history store.'
    required: true
  coverage-format:
    description: 'cobertura | coverage-py'
    required: false
    default: 'cobertura'
  risk-threshold:
    description: 'Minimum ML risk score to add a test outside direct coverage.'
    required: false
    default: '0.5'
  base-ref:
    description: 'Git ref to diff against (usually the PR base branch).'
    required: true
outputs:
  selected-tests:
    description: 'Newline-separated list of test IDs to run, priority-ordered.'
  estimated-time-saved:
    description: 'Estimated CI time saved vs. running the full suite, in seconds.'
runs:
  using: 'composite'
  steps:
    - run: python -m winnow.action
      shell: bash
```

## PR comment format (draft)

```md
### 🌾 Winnow test selection

**12 of 340 tests** selected for this change (est. **4m 20s** saved).

| Priority | Test | Reason |
|---|---|---|
| 1 | `test_pipeline_merges_deterministic_and_risk` | direct coverage overlap |
| 2 | `test_repository_get_recent` | direct coverage overlap |
| 3 | `test_risk_scorer_ranks_by_churn` | high co-change risk (0.78) |
| ... | ... | ... |

<sub>Coverage data incomplete for `winnow/new_module.py` — full suite ran as a safety fallback.</sub>
```

The "reason" column and the fallback footnote are non-negotiable: every
selection must be traceable to either direct coverage or an explicit risk
signal, and any safety fallback must be visible, not silent (ties to the
recall-safety requirement in the design spec).

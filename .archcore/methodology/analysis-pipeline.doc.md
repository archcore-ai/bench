---
title: "Analysis pipeline (analyze.py)"
status: accepted
tags:
  - "analysis"
  - "benchmark"
  - "pipeline"
---

## Overview

`scale/analyze.py` is the single entry point for turning raw CSV measurements into crossover tables, workload totals, and ASCII charts. It is a pure read-only script — it reads the CSV, computes derived fields, and prints output. Running it twice produces identical output for the same CSV.

Entry point: `python scale/analyze.py scale/results/results.csv`. Output order: summary → crossover table → ASCII chart → workload table.

## CSV Schema

Raw measurements written by `scale/run.sh` (via `grade.py`):

| Column | Type | Description |
|--------|------|-------------|
| `arm` | string | A / B1 / B2 / B3 / C |
| `phase` | string | crossover / workload |
| `trial` | int | Trial index (1-based) |
| `input_tokens` | int | Uncached input tokens |
| `cache_creation` | int | Tokens written to cache (billed at 1.25×) |
| `cache_read` | int | Tokens read from cache (billed at 0.10×) |
| `output_tokens` | int | Output tokens (billed at 5×) |
| `total_cost_usd` | float | Actually billed by API |
| `num_turns` | int | Number of agent turns |
| `duration_ms` | int | Wall-clock duration |
| `pass` | int | 1 if exact token match, 0 otherwise |
| `N` | int | KB size (number of docs loaded) |
| `task_id` | string | Identifier for the task (anchored to a facts.csv row) |

## Functions

### `load(csv_path)`

Reads the CSV and enriches each row with derived fields:

| Derived field | Formula |
|---------------|---------|
| `_ctx_in` | `input_tokens + cache_creation + cache_read` |
| `_cold` | `(_ctx_in × 3 + output_tokens × 15) / 1_000_000` |
| `_warm` | `total_cost_usd` |
| `_real` | See realistic formula below |
| `_err` | `1 if total_cost_usd == 0 else 0` |
| `_pass` | `pass` column cast to float |
| `_turns` | `num_turns` |
| `N` | `N` column cast to int |

Realistic formula applied per row:
```python
turns  = max(1, num_turns)
prefix = _ctx_in / turns
_real  = (prefix * (1.25 + 0.10 * (turns - 1)) * 3 + output_tokens * 15) / 1_000_000
```

### `agg(rows)`

Groups by `(phase, N, task_id, arm)`. For each group computes:
- **Median** of: `_real`, `_cold`, `_warm`, `_ctx_in`, `_turns`
- **Mean** of: `_pass`, `_err`

Filters: rows with `_ctx_in ≤ 1000` are excluded before aggregation (API errors / context overflows). Rows with high turn counts that still billed tokens are kept.

Returns a dict keyed by `(phase, N, task_id, arm)`.

### `crossover_table(rows)`

Filters `phase == "crossover"`. Pivots by N × arm. For each cell prints:
- Median realistic cost in dollars
- Pass rate (mean)
- Median context tokens
- Median turns

Output: Markdown table. Arms in column order: A / B1 / B2 / B3 / C.

### `workload_table(rows)`

Filters `phase == "workload"`. Arms B2, B3, C only. For each arm computes per-task medians (across trials), then sums across all task_ids. Reports:
- Suite total realistic cost
- Suite pass rate (mean of per-task means)
- Median turns per task

### `ascii_chart(rows)`

Filters `phase == "crossover"`. Plots realistic cost vs N as ASCII bar chart (one bar per arm per N value). Also shows cold/warm spread at N = max to give a sense of metric variance.

### `summary(rows)`

For each N in the crossover phase:
1. Filters to passing arms (pass_rate > 0).
2. Ranks arms by median realistic cost (ascending).
3. Computes crossover points between arm pairs via `_crossover_N`.

### `_crossover_N(baseline_series, challenger_series)`

Linear interpolation to find the N where challenger cost ≤ baseline cost.

```
Given two series {(N, cost)} for baseline and challenger:
1. At each N, compute delta = challenger_cost - baseline_cost.
2. Find the first adjacent pair (N_a, N_b) where sign changes (positive → non-positive).
3. Interpolate: crossover = N_a + (N_b - N_a) × |delta_a| / (|delta_a| + |delta_b|)
```

Returns `None` if no sign change is found in the tested N range (challenger never becomes cheaper).

### `main()`

Calls: `load` → `agg` → `summary` (printed first) → `crossover_table` → `ascii_chart` → `workload_table`.

## Extending the Pipeline

To add a new arm: add it to the arm ordering list and the column definitions in `crossover_table` and `workload_table`. The `load`/`agg` functions are arm-agnostic.

To add a new phase: add a filter branch in `crossover_table` or create a new function following the `workload_table` pattern. The `agg` dict key already includes `phase`.

To change the cost formula: update `load()` where `_real` is computed. The formula is applied once at row enrichment time; all downstream functions consume `_real` directly.

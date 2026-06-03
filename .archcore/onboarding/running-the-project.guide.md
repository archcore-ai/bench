---
title: "Running the project locally"
status: accepted
tags:
  - "onboarding"
---

## Prerequisites

```sh
archcore --version   # v0.4.x
claude --version     # 2.x
python3 --version    # 3.9+
```

## Steps

**1. Sanity check (2 min) — validates the harness on a 1-doc KB:**

```sh
bash harness/bench.sh
```

Default: `TRIALS=1`, `MODEL=sonnet`. Override via env: `TRIALS=3 MODEL=opus bash harness/bench.sh`.

**2. Full CLI benchmark (~90 min) — sweeps KB size 1–320 docs across 5 arms:**

```sh
cd scale
python3 gen_kb.py                        # generates 320-doc KB + facts.csv
bash run.sh all                          # crossover (N sweep) + workload (20-task suite)
python3 analyze.py results/results.csv   # crossover table, workload table, cost curves
```

Knobs: `MODEL` (default sonnet), `XTRIALS` (5), `WTRIALS` (3), `XSIZES` (1 20 80 160 320).

**3. Plugin benchmark (~60 min) — D-arm vs C-arm, 4 batch sizes:**

```sh
bash scale/run_plugin.sh
```

Knobs: `TRIALS` (default 3), `BATCH_SIZES` (1 2 4 8), `DOMAINS` (all 5).

Quick smoke test: `TRIALS=1 BATCH_SIZES="1 4" DOMAINS="middleware" bash scale/run_plugin.sh`

## Verification

```sh
column -t -s, results/results.csv                  # sanity results
column -t -s, scale/results/results.csv            # CLI benchmark (305 rows expected)
column -t -s, scale/results/plugin_results.csv     # Plugin benchmark (120 rows expected)
```

Expected: 100% pass rate, no rows with `ctx_in ≤ 1000`. Full analysis: `@ANALYSIS.md`.

## Common Issues

- **Auth errors:** ensure `claude` is logged in; `--strict-mcp-config` retains the default config dir for OAuth.
- **Wrong token counts:** confirm `--output-format json` is passed — counts come from `.usage`, not estimates.
- **Archcore not found:** `run.sh` expects `archcore` on PATH; check `archcore --version`.

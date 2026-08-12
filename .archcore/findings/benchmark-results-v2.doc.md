---
title: "Benchmark results v2 (archcore v0.7.0, plugin v0.7.1, CC 2.1.228)"
status: accepted
tags:
  - "benchmark"
  - "findings"
  - "plugin"
  - "results"
---

## Overview

Full re-measurement on 2026-08-12: archcore CLI v0.7.0, plugin v0.7.1, Claude Code 2.1.228,
model sonnet-5. 305 CLI + 120 plugin measurements. 100% pass rate on every arm carrying the
knowledge; arm A (cold floor) 0/25 as designed.

The headline ranking flipped versus v1 — Archcore went from the most expensive arm on the
workload suite to the cheapest by expected cost. **The cause is a Claude Code regression in the
baselines, not an Archcore improvement.** Arm C's own cost did not move: 142k to 144k context
tokens, cold $0.432 to $0.437.

## Content

### Three changes moved at once

| # | Change | Effect |
|---|--------|--------|
| 1 | `search_documents(mode=full)` shipped in CLI v0.7.0 | Arm C 5 turns to 3. Tokens unchanged. Latency -33%. |
| 2 | `/archcore:context` removed in plugin v0.7 | The v1 plugin benchmark measured a dead mechanism. Rebuilt. |
| 3 | Claude Code 2.1.228 regressed Grep/Read on large KBs | Baselines B2/B3 2.4-3.5x more expensive, and bimodal. |

### CLI - crossover

Arm C is flat and deterministic: **exactly 3 turns and 143-146k context tokens in all 25 runs**,
at every KB size from 1 to 320 documents. It is the only arm that does not move.

cold $/task, median (v1 to v2):

| N | B1 preload | B2 index+grep | B3 blind grep | C archcore |
|---|---|---|---|---|
| 1 | 0.081 / 0.139 | 0.164 / 0.569 | 0.244 / 0.174 | 0.433 / 0.434 |
| 80 | 0.190 / 0.290 | 0.175 / 0.297 | 0.252 / 0.184 | 0.432 / 0.441 |
| 320 | 0.545 / 0.784 | 0.224 / 0.741 | 0.254 / 1.350 | 0.432 / 0.435 |

Crossover points where C becomes cheaper - cold / realistic: vs B1 preload N~151 / N~12;
vs B2 N~106 / N~95; vs B3 N~94 / N~86. The metrics disagree sharply on B1 because B1 answers
in one turn and C in three. Quote the range, not one number.

Context-window overflow is no longer a preload risk: B1 at 320 docs uses 261k of sonnet-5's
1M window (26%). Preload's problem is purely cost now.

### CLI - workload (N=80, 60 runs per arm)

cold $ per task:

| Arm | median | mean | max | runs >2x median |
|-----|--------|------|-----|-----------------|
| B3 blind grep | 0.178 | 0.608 | 2.400 | 22/60 |
| B2 index+grep | 0.597 | 0.607 | 1.224 | 1/60 |
| C archcore | 0.437 | 0.470 | 0.635 | 0/60 |

**By median blind grep is 2.5x cheaper; by mean Archcore is 23% cheaper than both baselines.**
Same 60 runs. The difference is the tail.

Suite total (20 tasks): C $9.40 vs B2 $12.14 vs B3 $12.17 (cold, mean-based). Under the
realistic metric the ranking is identical: C $4.31 vs B2 $4.72 vs B3 $5.05.

Latency: C 8.8 s mean / 16.5 s max; B2 12.6 / 26.8; B3 16.3 / 93.4.

### Mechanism - B3 became bimodal

| Population | Share | Context | cold $ | Duration |
|---|---|---|---|---|
| lucky (<=2 turns) | 65% | 50k | 0.151 | 2 s |
| spiral (>2 turns) | 35% | 438k | 1.338 | 32 s |

In v1 there was no such split (83k / 3 turns on essentially every run). B2 degraded the same way
**despite carrying a perfect free index** - that an index-bearing arm regressed is the clearest
evidence the cause is host behaviour, not retrieval strategy.

### What mode=full actually bought

Arm C, workload, v1 to v2: turns 5 to 3, context 142k to 144k, cold $0.432 to $0.437, duration
12.0 s to 8.1 s, output 396 to 276 tokens. **Latency and turn count, not tokens.** Claiming a
token saving for `mode=full` is not supportable.

### Plugin - no measurable effect on retrieval cost

Plugin v0.7 replaced `/archcore:context` with a SessionStart hook injecting a ~150-token corpus
header (document counts, branch, tag vocabulary, tool pointer) - no document bodies. Verified
firing in headless `-p`: D quotes the CORPUS line, C answers NONE, so the control is clean.

120 runs, 0 errors, 100% pass. Turn counts identical at every batch size (3/3, 4/4, 6/6, 10/10).
Paired by (domain, trial), D is cheaper in 8/15, 3/15, 7/15, 8/15 pairs at batch 1/2/4/8 - chance
level, with the single deviation running against the plugin. Paired median context delta:
-82 / +2,444 / +73 / -11 tokens, i.e. within noise of the injection itself.

Session batching still works and is worth using - cold $/question 0.461 (N=1) to 0.132 (N=4) to
0.074 (N=8), -84%. **Both arms get it equally.** The v1 report credited this to the plugin; it
is a property of batching questions into one session.

### Claims retired from v1

- "Plugin is 10% cheaper than raw MCP at N=4" - was about `/archcore:context`, which no longer
  exists; on the v0.7 mechanism the effect is nil.
- "Plugin gives 8-12x tighter cost variance" - not reproduced; D and C ranges overlap everywhere.
- "Archcore is at rough parity with files+grep" - no longer true in either direction: worse by
  median, better by mean.
- "At ~27 documents Archcore becomes cheaper than CLAUDE.md preload" - now ~100-150 (cold) or
  ~12 (realistic); the old single number is not defensible.

## Examples

Reproduce:

```bash
cd scale
MAXTURNS=20 CSV=$PWD/results/results_v2.csv bash run.sh all
python3 analyze_v2.py results/results_v2.csv results/results_v1.csv
PLUGIN=/path/to/plugin bash run_plugin_v7.sh
```

Raw data: `scale/results/results_v2.csv` (305 rows), `scale/results/plugin_results_v7.csv`
(120 rows). v1 preserved at `results_v1.csv` / `plugin_results.csv`.

## Caveats

Host-version sensitivity is now a first-order effect: baselines changed 2.4-3.5x across one
Claude Code minor range with no change to KB, task, or model. Every cross-arm number is valid
for a stated host version only. Absolute costs are not comparable across v1 and v2 either - the
host system prompt grew ~19k tokens (B1 at N=1: 27k to 46k).

5 trials per crossover cell is thin now that two arms are bimodal; distribution claims rest on
the workload phase (60 runs/arm).

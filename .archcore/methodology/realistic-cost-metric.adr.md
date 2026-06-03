---
title: "Use realistic per-task cost as the headline metric"
status: accepted
tags:
  - "benchmark"
  - "cost-metric"
  - "methodology"
---

## Context

Measuring the token cost of a `claude -p` run is complicated by prompt caching, which creates two distinct confounders:

**Confounder 1 — cold over-charges multi-turn arms.** The naive metric charges `ctx_in × $3/M + output × $15/M` where `ctx_in = input + cache_creation + cache_read`. This treats every turn as if it re-bills the full context at the uncached input rate. Arm C (archcore) runs 5 turns per task; arms B2/B3 run 2-3. The cold metric systematically over-penalizes retrieval-based arms relative to preload.

**Confounder 2 — warm is order-dependent.** The actually-billed `total_cost_usd` is polluted by cross-run cache bleed: sequential `claude -p` invocations within a trial batch share cache state, so later runs pay cache_read prices even though they model independent user sessions. The warm metric understates preload cost when runs are batched.

**First-version consequence.** The v1 harness used the cold metric as the headline number. This made the C-vs-B1 crossover appear at approximately 207 docs instead of the correct value of approximately 27 docs — a 7.7× error that would lead to the wrong practical recommendation.

## Decision

Use the **realistic per-task cost** as the single headline metric for all crossover and workload comparisons:

```
turns    = max(1, num_turns)
prefix   = ctx_in / turns                # avg per-turn context size
realistic = prefix × (1.25 + 0.10 × (turns − 1)) × $3/M
           + output_tokens × $15/M
```

Multipliers reflect Sonnet 4.x cache pricing: 1.25× for cache_creation (first turn), 0.10× for cache_read (subsequent turns within the same CLI call).

**What the formula models:** a fresh session per task (cache cold at each task boundary, so the first turn is always cache_creation priced), but consecutive turns within a single `claude -p` call are cache hits (charged at the read rate). This is the real usage pattern: a user issues one task, gets an answer, starts a new session for the next task.

Also compute and report cold and warm as bounds. Cold is the transparent upper bound; warm is the lower bound actually billed. Realistic is the number to use in crossover tables and workload totals.

## Alternatives

**Cold metric alone** — Simple and reproducible, but systematically over-charges multi-turn arms by 3-5× at the typical turn counts observed (3-5 turns for C, 2-3 for B2/B3). Produces misleading crossover points.

**Warm metric alone** — Reflects actual billing but is order-dependent. Running trials in alphabetical arm order gives arm A cache benefits from arm C's preceding run. Not reproducible without controlling run order and cache state, which is impractical across benchmark re-runs.

**Count tokens, not dollars** — Token counts are also caching-sensitive (cache_read tokens cost 0.1× of input tokens). Dollar cost is the right primary metric because it combines input/output asymmetry and cache discounts in one number. Token counts are useful secondary diagnostics.

## Consequences

- All future benchmark runs MUST use the realistic formula with the same multipliers (1.25 / 0.10) and the same Sonnet 4.x price basis ($3/M input, $15/M output) to be directly comparable to v1 results.
- If cache pricing changes or a different model is used, the formula constants MUST be updated and the run MUST be labeled with the new pricing basis; it MUST NOT be compared directly against v1 crossover numbers.
- The correction moved the C-vs-B1 crossover from ~207 docs (cold) to ~27 docs (realistic). Any analysis quoting the ~207 figure is using the wrong metric.
- `analyze.py` computes all three metrics; crossover tables and workload totals display realistic as the primary column, with cold and warm available for diagnostic reference.

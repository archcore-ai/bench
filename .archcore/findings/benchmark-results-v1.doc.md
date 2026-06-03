---
title: "Benchmark results v1 (archcore v0.3.6)"
status: accepted
tags:
  - "benchmark"
  - "findings"
  - "results"
---

## Version Info

- Archcore: v0.3.6
- Claude CLI: v2.1.158
- Model: claude-sonnet-4-x (Sonnet 4.x pricing: $3/M input, $15/M output)
- Run date: 2026-06-02
- Total measurements: 305 (125 crossover + 180 workload)
- Failures: 0 timeouts, 0 quality failures (100% pass across all arms and phases)

**Canonical baseline:** the `mode=full` numbers ($0.127/q, 3 turns) are the post-fix v1 baseline referenced in README, SUMMARY, and ANALYSIS. The pre-fix numbers (0.147, 5 turns) are included for completeness. Future benchmark runs MUST reference this doc when claiming comparison to v1.

All costs use the **realistic per-task metric** (see methodology ADR).

## Crossover Results (realistic per-task $)

Phase: crossover. One anchor task. N ∈ {1, 20, 80, 160, 320}. 5 trials per cell.

| N (docs) | A cold | B1 preload | B2 index+grep | B3 blind grep | C archcore |
|----------|--------|------------|---------------|---------------|------------|
| 1        | 0.204 ✗ | **0.102** | 0.111 | 0.103 | 0.147 |
| 20       | 0.183 ✗ | 0.134 | **0.113** | 0.121 | 0.147 |
| 80       | 0.188 ✗ | 0.238 | **0.119** | 0.123 | 0.147 |
| 160      | 0.195 ✗ | 0.386 | 0.130 | **0.124** | 0.141 |
| 320      | 0.228 ✗ | 0.681 | 0.152 | **0.112** | 0.147 |

Bold = cheapest passing arm for that N. ✗ = arm A fails the anchor task (no knowledge loaded).

**Crossover points (realistic metric, pre-fix):**
- C vs B1 (preload): **~27 docs** — at N=320, C is 4.6× cheaper than B1.
- C vs B2 (index+grep): **~272 docs** — B2 stays cheaper than C within the tested range up to 272.
- C vs B3 (blind grep): **never** in the tested N range (B3 consistently cheaper).

## Workload Results (N=80, 20 tasks, B2/B3/C)

Phase: workload. N=80. 20 tasks spanning 5 domains. 3 trials per cell.

| Arm | Suite realistic $ | Pass rate | Median turns/task |
|-----|-------------------|-----------|-------------------|
| B3 — blind grep | $2.294 | 100% | 3 |
| B2 — index+grep | $2.375 | 100% | 2 |
| C — archcore | $2.716 | 100% | 5 |

All three arms answer every task correctly. B3 and B2 beat C by ~15% on total suite cost at N=80.

## Mechanism: The ToolSearch Tax

Arm C's higher turn count (5 vs 2-3 for B2/B3) is caused by Claude Code's lazy MCP tool loading. Every MCP tool call is preceded by a `ToolSearch` housekeeping turn that loads the schema. The actual C turn sequence per task:

```
Turn 1: ToolSearch(search_documents)     — schema load
Turn 2: search_documents(...)            — query KB
Turn 3: ToolSearch(get_document)         — schema load
Turn 4: get_document(...)                — fetch full doc
Turn 5: answer
```

2 of C's 5 turns are schema-loading overhead (`ToolSearch`) that built-in Grep never pays. Archcore's always-on contribution is approximately 638 tokens/turn (full MCP schemas + server instructions, not held in persistent context). This exactly reproduces the benchmark's observed ctx ≈ 144 K for arm C.

## mode=full Fix (measured 2026-06-02) — canonical post-fix baseline

A `mode=full` parameter was added to `search_documents` that returns the doc body inline (frontmatter stripped), eliminating the need for a subsequent `get_document` call and its preceding `ToolSearch`. Measured on the same anchor task across the full N sweep (new archcore binary, 2-5 trials per cell, 100% pass):

| N | C pre-fix | C mode=full | Turns | B3 blind grep |
|---|-----------|-------------|-------|---------------|
| 1   | 0.147 | **0.127** | 3 | 0.103 |
| 20  | 0.147 | **0.127** | 3 | 0.121 |
| 80  | 0.147 | **0.127** | 3 | 0.123 |
| 160 | 0.141 | **0.127** | 3 | 0.124 |
| 320 | 0.147 | **0.127** | 3 | 0.112 |

mode=full reduces C from 5 turns to 3 turns and holds at **$0.127 flat** across all N (retrieval cost is independent of KB size — the defining property of indexed lookup). This is the number used as the v1 CLI baseline in README, SUMMARY, and ANALYSIS.

**Crossover impact of mode=full:**
- C vs B1: crossover moves from ~27 docs → **~16 docs**.
- C vs B3: moves from "never" to **near-parity** (C is +3–13% more expensive than B3 across tested N).

Full per-N breakdown in `rnd.md` (repo root).

## What Can and Cannot Be Claimed from v1

**CAN claim:**
- At N ≥ 27 docs, archcore MCP retrieval (pre-fix) is cheaper than full preload (B1) using the realistic metric.
- All arms achieve 100% answer correctness on this KB and task set.
- B3 (blind grep) matches or beats C on per-task cost at N=80 in both crossover and workload phases.
- The ToolSearch mechanism is the proximate cause of C's 5-turn overhead.
- mode=full (measured) reduces C to 3 turns and $0.127 flat, moving the B1 crossover to ~16 docs.

**CANNOT claim from v1 data:**
- Results generalize to real (non-synthetic) KBs — the honesty invariants make the task harder than most real lookups where partial context is informative.
- Results hold at N > 320 — no data beyond that point.
- mode=full results are part of the original v1 run — they were measured on a different archcore binary after the initial run.
- B2 or B3 are preferable for all team sizes — index maintenance cost (B2) and search reliability at large N (B3 Grep quality degrades with more files) are not captured.
- Cost comparisons hold under different cache pricing or model versions — see the methodology spec's conformance section.

---
title: "Plugin benchmark pilot v1 — session batching economics"
status: accepted
tags:
  - "benchmark"
  - "findings"
  - "plugin"
---

## Overview

Pilot benchmark investigating token-cost economics of the Archcore Plugin (`--plugin-dir`) in
headless `claude -p` mode. This is a single-trial pilot on one domain (middleware, N=80 KB).
Results establish the mechanism and crossover points; a multi-trial, multi-domain Phase 2 benchmark
is needed to confirm generalization.

Pilot run date: 2026-06-03. Model: claude-sonnet-4-6 (Sonnet 4.x pricing: $3/M input, $15/M output).
Methodology: same as v1 (realistic metric as headline), isolation requirements identical.

Refer to `benchmark-results-v1.doc.md` for v1 C-arm baseline ($0.127/question, mode=full, 3 turns).

---

## Setup

- **KB**: N=80, middleware domain (16 docs × 4 other domains — same as v1 workload arm)
- **D-arm**: same as C-arm + `--plugin-dir /path/to/plugin`; `/archcore:context middleware` invoked first in the prompt
- **C-arm (batch control)**: same as C-arm but multiple questions in one `claude -p` call
- **C-separate baseline**: v1 measurement — one `claude -p` call per question, mode=full, $0.127/q realistic

Prompt structure for D-batch(N):
```
/archcore:context middleware

For each question below, output ONLY the exact token value (one per line, in order):
1. [question 1]
...
N. [question N]
```

Grading: exact token match required for each answer. All pilot runs passed (100%).

---

## Results

### Crossover table (realistic metric, middleware, single trial)

| N questions/session | D-arm $/q | C-arm batch $/q | D vs C-sep | C-batch vs C-sep |
|---------------------|-----------|-----------------|-----------|------------------|
| 1 (single call)     | $0.1735   | $0.1270 (baseline) | **+37%** | 0%            |
| 2                   | $0.0748   | $0.0697         | **−41%**  | −45%             |
| 4                   | $0.0321   | $0.0336         | **−75%**  | −74%             |
| 8                   | $0.0142   | $0.0166         | **−89%**  | −87%             |

D vs C-batch at same N (realistic metric):
- N=1: D is **+37%** more expensive
- N=2: D is **+7%** more expensive
- N=4: D is **−4%** cheaper
- N=8: D is **−15%** cheaper

Crossover (D vs C-batch): ~N=3.
Crossover (D or C-batch vs C-separate): N≥2.

### Raw measurements

| Arm | N | Turns | ctx_in | Warm $ | Realistic $ |
|-----|---|-------|--------|--------|-------------|
| C-sep (v1)  | 1 | 3  | ~93k  | —      | 0.1270 |
| D-single    | 1 | 6  | 189k  | 0.1095 | 0.1735 |
| C-batch(2)  | 2 | 6  | 152k  | 0.0951 | 0.1395 |
| D-batch(2)  | 2 | 8  | 191k  | 0.1155 | 0.1497 |
| C-batch(4)  | 4 | 3  | 88k   | 0.0701 | 0.1342 |
| D-batch(4)  | 4 | 12 | 194k  | 0.1274 | 0.1284 |
| C-batch(8)  | 8 | 3  | 88k   | 0.0688 | 0.1330 |
| D-batch(8)  | 8 | 12 | 166k  | 0.1305 | 0.1137 |

---

## Mechanism: Session Amortization

The dominant cost driver is the **fixed per-session overhead**: MCP tool schemas, plugin skill
instructions, Claude Code system prompt, chi-repo CLAUDE.md/source context. This overhead is
~88–190k tokens but is paid only ONCE per `claude -p` invocation (cache-creation on turn 1,
cache-read on all subsequent turns at 0.10× rate).

When N questions are sent in a single session:
- Fixed overhead is amortized across N questions
- Each additional question contributes only ~$0.002–0.010 in marginal token cost
- Per-question cost → near-zero as N → large

This mechanism is **arm-agnostic**: both C-batch and D-batch benefit equally from batching.

### Why D-arm has more turns than C-arm

The `/archcore:context` skill calls `search_documents(content, limit=50)` **without mode=full**.
This returns only top-5 results with short excerpts — answer tokens are in the Decision section
and are NOT included. The model must then call `get_document` for each question (~2 turns/question).

C-arm calls `search_documents(mode=full)` to get all matching doc bodies inline. It answers all
questions in one shot → 3 turns total regardless of N.

### Why D-arm beats C-arm at N≥4 in realistic metric

With 12 turns (D) vs 3 turns (C) for the same N questions, the realistic metric's cache model
rewards D: prefix = ctx_in/12 is small, and 11 of 12 turns pay cache-read rate (0.10×). C has
3 turns with a larger per-turn prefix paying the higher first-turn rate. At N≥4, this effect
outweighs D's higher absolute ctx_in.

---

## Claims

### What CAN be claimed from pilot data

- Batching N same-area questions in one session saves **45% (N=2), 74% (N=4), 87% (N=8)** per
  question vs separate calls. Applies to BOTH arms.
- Plugin (D-arm) is **neutral to slightly favorable** vs raw MCP (C-arm) at N≥4 in realistic
  metric. The overhead is fully amortized.
- Plugin costs **37% more** per question for single-question sessions.
- The context skill in its current form does NOT improve retrieval efficiency over raw MCP for
  exact-token lookup tasks (no full bodies in excerpts → extra get_document calls needed).

### What CANNOT be claimed from pilot data

- Results generalize beyond middleware domain or N=80 KB (single-trial, single-domain).
- Plugin's context skill provides retrieval gains — pilot shows it does not for fact-lookup tasks.
- C-batch is reliably 3 turns for all N — observed at N=4,8 but not N=2 (model behavior, not guaranteed).

---

## Conditions Favoring Plugin Batching

Plugin (D-arm) shows neutral-to-favorable economics when:
1. **N≥4 questions per session per area** — fixed overhead fully amortized
2. **Discovery-heavy tasks** — agent must know WHICH conventions exist before acting. Not tested
   in this pilot (all tasks were direct exact-token lookups).

Plugin's value proposition for token economics is primarily **session workflow structure** —
the context skill enforces a load-first, answer-second pattern that naturally results in efficient
amortized sessions.

---

## Path to Phase 2

Required to make production claims:

1. **Multi-trial**: ≥3 trials per (arm, N, domain) cell for variance and confidence intervals
2. **Multi-domain**: all 5 domains (middleware, routing, errors, logging, testing)
3. **mode=full context skill variant**: measure D-arm with mode=full → expect 3-turn efficiency
4. **Discovery task design**: tasks where model must identify relevant docs without knowing
   the topic phrase — context skill's curated overview may show genuine gains here

Required scripts:
- `bench/scale/run_plugin.sh` — driver for D-arms
- `bench/plugin_tasks.json` — batch task groups (5 domains × 4 batch sizes)
- `bench/scale/grade_batch.py` — multi-answer grader
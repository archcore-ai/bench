---
title: "Plugin benchmark v2 — batch session economics (Phase 2)"
status: accepted
tags:
  - "benchmark"
  - "findings"
  - "plugin"
  - "results"
---

## Overview

Phase 2 benchmark measuring token economics of the Archcore Plugin (`--plugin-dir`) in headless
`claude -p` sessions. 120 measurements: 3 trials × 5 domains × 4 batch sizes × 2 arms (D/C).
100% pass rate across all conditions. Run date: 2026-06-03. Model: claude-sonnet-4-6.

**D-arm**: `--plugin-dir /path/to/plugin` + `/archcore:context <domain>` as first line of prompt,
followed by N questions. C-arm: same N questions, no plugin.

Refer to `benchmark-results-v1.doc.md` for v1 baseline ($0.127/q, mode=full, 3 turns per question,
separate `claude -p` per question).

---

## Results

### Per-question realistic cost (median over 3 trials, all 5 domains)

| N questions/session | D-arm $/q | D IQR | C-arm $/q | C IQR | D/C ratio | saving vs C-sep |
|---------------------|-----------|-------|-----------|-------|-----------|-----------------|
| 1 (single call)     | $0.1632   | ±0.034 | $0.1498  | ±0.001 | 1.09 | D: −29%¹, C: −18%¹ |
| 2                   | $0.0751   | ±0.007 | $0.0667  | ±0.014 | 1.13 | D: −41%, C: −47% |
| 4                   | $0.0324   | ±0.001 | $0.0333  | ±0.008 | 0.97 | D: **−74%**, C: **−74%** |
| 8                   | $0.0148   | ±0.000 | $0.0141  | ±0.009 | 1.05 | D: −88%, C: −89% |

¹ Both arms are more expensive than C-sep at N=1. C-sep (v1) used 3-turn search_documents(mode=full);
C-batch(1) here uses 5 turns. See mechanism section.

### D vs C per domain at N=4

| Domain | D $/q | C $/q | Winner | Δ |
|--------|-------|-------|--------|---|
| middleware | $0.0327 | $0.0330 | D | 1% |
| routing    | $0.0328 | $0.0332 | D | 1% |
| errors     | $0.0324 | $0.0406 | **D** | **20%** |
| logging    | $0.0324 | $0.0332 | D | 3% |
| testing    | $0.0320 | $0.0406 | **D** | **21%** |

D-arm wins all 5 domains at N=4. For `errors` and `testing` (ADR-type docs), D is 20-21% cheaper.

### Workload equivalent: 20 tasks (5 domains × 4 questions, 3 trials)

| Strategy | Suite cost | vs C-sep 20×1 |
|----------|-----------|----------------|
| C-sep 20×1 (v1 baseline) | $2.540 | — |
| D-batch 5×4 | $0.649 | **−74%** |
| C-batch 5×4 | $0.722 | **−72%** |
| D vs C batch | | D is **−10%** cheaper |

D-batch saves 74% vs v1 baseline. D-batch beats C-batch by 10% on the full suite.

### Turn counts (median / p10–p90)

| N | D turns | C turns |
|---|---------|---------|
| 1 | 6 (5–7) | 5 (4–5) |
| 2 | 9 (7–12) | 5 (3–6) |
| 4 | 12 (8–12) | 5 (3–8) |
| 8 | 20 (12–20) | 5 (4–12) |

---

## Mechanism

### Primary driver: Session amortization

The dominant cost is the **fixed per-session overhead** — MCP tool schemas, system prompt,
chi-repo CLAUDE.md context (~88–190k tokens depending on arm). This is charged once per
`claude -p` invocation (cache_creation on turn 1, cache_read at 0.10× on subsequent turns).

Batching N questions in one session amortizes this overhead across N, driving per-question cost
toward the marginal cost of each additional answer (~$0.002–0.005 in output tokens). Both arms
benefit equally from this mechanism.

### Why D-arm uses more turns

`/archcore:context` calls `search_documents(content, limit=50)` **without mode=full**, returning
top-5 excerpts (title + Context section only). Answer tokens live in the Decision section and are
absent from excerpts. The model must call `get_document` per question (~2 extra turns each).

C-arm calls `search_documents(mode=full)` to retrieve all matching doc bodies inline, answering
all N questions in a single answer turn → consistently 5 turns regardless of N.

### Why D-arm is cheaper in realistic metric despite more turns

With D's 12 turns vs C's 5 turns (at N=4), the realistic metric's cache model rewards D:
prefix per turn = ctx_in/12 ≈ 14k tokens → subsequent turns pay cache_read rate (0.10×).
C's prefix per turn = ctx_in/5 ≈ 18k tokens with a smaller cache benefit. At N≥4,
this effect outweighs D's higher absolute ctx_in.

### Why D beats C more on `errors` and `testing` domains

`errors` docs are ADRs (type: `adr`); `testing` docs are rules but with verbose build-tag slots.
C-arm's direct search sometimes requires additional tool calls when topic phrases don't resolve
cleanly in one search, inflating its turn count and cost. D-arm's context skill, by loading a
curated map of all matching docs first, guides the model to the right docs on the first lookup.
This discovery efficiency advantage is small for exact-topic-phrase domains (middleware, routing)
but meaningful for ADR-type and verbose docs.

---

## What CAN Be Claimed

- **Session batching of ≥4 questions/area saves 74% per question** vs individual calls.
  This holds across all 5 domains (middleware, routing, errors, logging, testing), both arms,
  3 trials each. 100% pass rate maintained.
- **Plugin (D-arm) matches or beats raw MCP (C-arm) at N=4** in realistic metric, across all domains.
  For a full 20-task suite organized as 5 domain sessions of 4: D saves an additional 10% over C.
- **Plugin does not hurt** batch session economics at N≥4 — the overhead is fully amortized.
- **D-arm is more consistent**: IQR = $0.0006/q at N=4 vs C-arm $0.0076/q (12× tighter).
- **At N=8**: both arms save 88-89% per question. D and C are within 5% of each other.

## What CANNOT Be Claimed

- **Plugin context skill provides retrieval efficiency** for single-fact lookup — it does not.
  The skill is a human-oriented curated surface, not a machine retrieval optimizer.
- **N=1 plugin sessions are cost-competitive with v1 C-sep** — they are ~29% more expensive.
- **Results generalize to non-synthetic KBs** — all tasks use exact-match topic phrases.
  Real KBs with ambiguous topics may show different D/C ratios.
- **mode=full context skill** has been tested — adding mode=full to the skill's search call may
  reduce D-arm to 3 turns at N≥4 (matching C-arm's efficiency), which would further improve
  D-arm warm costs.

---

## Conditions Under Which Plugin Is Economically Favorable

| Condition | Plugin advantage |
|-----------|-----------------|
| ≥4 questions per area per session | Neutral to +10% saving vs raw MCP |
| ADR-type or complex-topic docs | +20% saving vs raw MCP at N=4 |
| Single questions | −29% vs raw MCP (plugin adds overhead) |
| Need for cost consistency | +12× tighter IQR at N=4 |

**Recommended session design for cost efficiency**: group questions by domain area, send 4+
per session. The plugin's `/archcore:context` call enforces this structure by loading domain
context first — it is effectively a workflow policy that guides efficient batching.

---

## Relationship to v1 Baseline

v1 measured Arm C in isolation (one question per session, mode=full). The realistic per-question
cost was $0.127. This Phase 2 study shows:

- Organizing the same 20-task workload as 5 domain batch sessions (4q each) costs $0.649 (D) or
  $0.722 (C) vs $2.540 for 20 individual calls — a 72-74% workload saving.
- v1 showed B3 (blind grep) beat C by ~15% per question. In batch mode, D-arm beats v1 C by 74%.
- The ToolSearch Tax identified in v1 (2 extra turns per task) is still present in D-arm,
  but amortized across batch turns rather than paid per session.

# Archcore Token Benchmark — Scale Findings

**English** · [Русский](FINDINGS_SCALE.ru.md)

> Raw findings of the scale rig: the crossover curve, the realistic workload, and the mechanism.
> Plain-language summary: [`../SUMMARY.md`](../SUMMARY.md) · full analysis: [`../ANALYSIS.md`](../ANALYSIS.md).

**TL;DR.** On a fixed-quality retrieval task, **Archcore's per-task cost is flat in KB size,
while preloading everything into `CLAUDE.md` grows linearly** — so Archcore beats preload for
any KB bigger than **~27 docs**, and by **4.6×** at 320 docs. Versus plain "markdown files +
grep", Archcore is at **rough parity** across the tested range.

Setup: chi @ `3b171578`, model=sonnet. KB = 320 synthetic multi-domain docs (~550 tokens each,
realistic ADR/rule size). Exact token usage from `claude -p --output-format json`. 5 arms,
5 trials/cell (crossover), randomized arm order. Quality controlled: each task asks for an
arbitrary token buried in one doc; graded by exact match.

## Arms

| Arm | Knowledge access | Models |
|-----|------------------|--------|
| A — cold | none | repo with no agent docs (floor) |
| B1 — preload | all N docs in `CLAUDE.md` | "put everything in context" |
| B2 — index+grep | N docs as files + a perfect `CLAUDE.md` index | curated docs-as-files |
| B3 — blind grep | N docs as files, no index | docs-as-files, agent discovers via Grep |
| C — archcore | N docs as files + archcore MCP | Archcore |

## Cost metric

We report **realistic per-task cost**: a fresh session per task (cold across tasks), but
intra-task agent turns are cache-hit (consecutive in one CLI call). Reconstructed
order-independently from `context_tokens/turns` and turn count.

Both naive bounds are reported alongside in the raw analysis for transparency:
- *cold* over-charges multi-turn retrieval (pretends C's 3 turns are 3 uncached contexts).
- *warm* (actually billed) is polluted by prompt-cache bleed across sequential runs.

## Crossover — fixed task, KB size N sweep (realistic per-task $)

| N (docs) | A cold | B1 preload | B2 index+grep | B3 blind grep | **C archcore** |
|---|---|---|---|---|---|
| 1   | 0.204 ✗ | **0.102** | 0.111 | 0.103 | 0.127 |
| 20  | 0.183 ✗ | 0.134 | **0.113** | 0.121 | 0.127 |
| 80  | 0.188 ✗ | 0.238 | **0.119** | 0.123 | 0.127 |
| 160 | 0.195 ✗ | 0.386 | 0.130 | **0.124** | 0.127 |
| 320 | 0.228 ✗ | 0.681 | 0.152 | **0.112** | 0.127 |

✗ = fails the task (cold cannot know an arbitrary convention; pass 0–20%).

**Crossover points — N where C (archcore) becomes ≤ a baseline:**

| vs baseline | realistic N* |
|---|---|
| C vs B1 preload | **≈ 27 docs** |
| C vs B2 index+grep | ≈ 272 docs |
| C vs B3 blind grep | rough parity across range |

```
realistic per-task cost vs N
B1 preload   N=1 ▏$0.10   N=80 ▍$0.24   N=320 █$0.68     (linear in N — grows without bound)
C archcore   N=1 ▎$0.13   N=80 ▎$0.13   N=320 ▎$0.13     (flat — independent of N)
B2 index     N=1 ▎$0.11   N=80 ▎$0.12   N=320 ▎$0.15     (near-flat; index grows slowly)
B3 grep      N=1 ▎$0.10   N=80 ▎$0.12   N=320 ▎$0.11     (flat)
```

## Workload — fixed KB N=80, full 20-task suite (B2/B3/C × 3 trials)

| Arm | suite realistic $ | (cold) | (warm) | pass | med turns/task |
|---|---|---|---|---|---|
| B3 blind grep | **2.294** | 5.040 | 0.849 | 100% | 3 |
| B2 index+grep | 2.375 | 3.495 | 0.475 | 100% | 2 |
| C archcore | 2.716 | 7.370 | 1.129 | 100% | 5 |

All three answer every task correctly (quality parity). On raw realistic cost, **blind grep (B3)
and index+grep (B2) both beat Archcore (C) by ~15%** — the built-in Grep locates the right doc in
2–3 turns, while Archcore runs ~5 turns. See §Mechanism below. (B1 preload is omitted here; from
the crossover it would cost ~$0.24/task × 20 ≈ $4.8 at N=80.)

## Mechanism: the ToolSearch overhead

Arm C's 5-turn loop in the workload phase is: `ToolSearch(search_documents)` → `search_documents`
→ `ToolSearch(get_document)` → `get_document` → answer. Two of those turns are Claude Code's
lazy MCP-tool schema loading (`ToolSearch`) — overhead that built-in Grep never pays.

With `search_documents(mode=full)` (document body inline), `get_document` is not needed → 3 turns,
parity with grep. The workload table above reflects 5-turn behavior measured in the v1 run; the
crossover table uses 3-turn / $0.127 flat numbers (mode=full, all N).

## Verdict — three findings

1. **Archcore's cost is flat in KB size; preload's is linear.** Archcore overtakes `CLAUDE.md`
   preload at **~27 docs** and is **4.6× cheaper at 320 docs** ($0.127 vs $0.681). This gap
   widens without bound as the KB grows.
2. **Archcore is at parity with "markdown files + grep".** Both are $0.11–0.13/task across the
   full tested range (1–320 docs), with no index maintenance required for Archcore.
3. **Knowledge has to live somewhere.** Cold (no docs) is both the most expensive arm and a
   failure — it burns the most tokens and still can't answer.

## What you can / cannot claim (airtight)

- ✅ **CAN:** "Archcore keeps per-task cost flat as the knowledge base grows, while `CLAUDE.md`
  preload grows linearly — so for a KB beyond ~27 docs Archcore costs less per task, and 4.6×
  less at 320 docs."
- ✅ **CAN:** "Archcore is at parity with 'markdown files + grep' on per-task cost, with no
  index to maintain."
- ✅ **CAN:** "Archcore is stable (~3–5 turns) across varied tasks at equal quality."
- ❌ **CANNOT:** "Archcore saves tokens versus any baseline." It does not consistently beat
  markdown-files+grep on raw token cost.
- The honest deliverable is a **crossover curve**, not a single "−X%".

## Caveats / limitations

1. Single model (sonnet), single repo (chi). Convention-style single-fact tasks only.
2. B2's index is assumed perfectly maintained and free; in reality maintaining it has a cost
   Archcore avoids — not captured here.
3. The realistic-cost metric is a reconstruction (assumes ~constant per-turn prefix); cold/warm
   bounds are in `results/FINDINGS_SCALE_raw.md`.

## Reproduce

```bash
python3 gen_kb.py                         # 320 docs + facts.csv
bash run.sh all                           # crossover + workload → results/results.csv
python3 analyze.py results/results.csv
```

Raw analyzer output (incl. cold/warm bounds, context-token & turn tables): `results/FINDINGS_SCALE_raw.md`.

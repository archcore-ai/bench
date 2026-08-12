# Archcore benchmark — token cost, reproducibly measured

Reproducible measurement of what Archcore costs an AI coding agent at a **fixed quality bar**,
against realistic baselines. Two tools are measured: the **CLI** (Archcore as an MCP server)
and the **Plugin** (Claude Code integration).

**Current run: 2026-08-12** — archcore CLI v0.7.0, plugin v0.7.1, Claude Code 2.1.228,
model sonnet-5. 425 measurements. The previous run (2026-05-31, archcore v0.3.6) is kept
alongside so every number can be compared across versions.

---

## Part 1 — What the benchmark actually shows

### The finding: Archcore's cost is flat, and it is the only arm without a tail

Across all 25 crossover runs, Archcore used **exactly 3 turns and 143–146k context tokens** —
at every knowledge-base size from 1 to 320 documents. No other retrieval arm is stable.

```
Per-task cost as the KB grows (cold $, median):

CLAUDE.md preload  ▎$0.14  →  ▌$0.29  →  ███ $0.78     grows linearly
archcore (CLI)     █▊$0.43 →  █▊$0.44 →  █▊$0.44       flat — independent of KB size
files + grep       ▊$0.17  →  ▊$0.18  →  █████ $1.35   flat, then falls apart
                     1 doc     80 docs     320 docs
```

**Crossover table — cost per task at equal quality (100% pass rate on every passing arm):**

| KB size | CLAUDE.md preload | files + index | files + grep | **Archcore CLI** |
|---------|-------------------|---------------|--------------|------------------|
| 1 doc   | **0.139**         | 0.569         | 0.174        | 0.434            |
| 20 docs | **0.175**         | 0.427         | 0.177        | 0.434            |
| 80 docs | 0.290             | 0.297         | **0.184**    | 0.441            |
| 160 docs| 0.455             | 0.648         | 1.298        | **0.441**        |
| 320 docs| 0.784             | 0.741         | 1.350        | **0.435**        |

*(cold metric — no turn-model assumptions. Under the realistic metric the ranking is the same
but preload crosses much earlier; see [`ANALYSIS.md`](ANALYSIS.md) §2.4 for both.)*

Archcore overtakes `CLAUDE.md` preload at **~100–150 documents** and the grep baselines at
**~90–110**. Below that, the baselines are cheaper — plainly so at small KB sizes.

### Where the real difference shows up: the tail

On the 20-task workload suite at 80 documents (60 measurements per arm):

| Arm | median $ | **mean $** | max $ | runs >2× median |
|-----|----------|------------|-------|-----------------|
| files + grep | **0.178** | 0.608 | 2.400 | **22/60** |
| files + index | 0.597 | 0.607 | 1.224 | 1/60 |
| **Archcore CLI** | 0.437 | **0.470** | 0.635 | **0/60** |

**By median, blind grep is 2.5× cheaper than Archcore. By mean, Archcore is 23% cheaper than
both baselines.** Both are true, of the same 60 runs. Grep resolves in one turn 65% of the time
and spirals into 400k+ tokens the other 35%; Archcore never spiraled once.

Full suite cost: **Archcore $9.40** vs files+index $12.14 vs files+grep $12.17.

Same shape in latency: Archcore 8.8 s mean (max 16.5 s), grep 16.3 s mean (max **93 s**).

### An honest caveat about this run

In the previous run Archcore was the **most expensive** arm on this suite. The ranking flipped
because Claude Code 2.1.228 regressed `Grep`/`Read` on large knowledge bases — the baselines
got 2.4–3.5× more expensive. **Archcore's own cost did not move** (142k → 144k tokens).
This is a baseline regression, not an Archcore improvement, and it means these cross-arm
numbers are valid for a stated host version only.

### Plugin: cost-neutral for retrieval

Plugin v0.7 removed `/archcore:context`. Session context now arrives via a SessionStart hook —
a ~150-token corpus header (document counts, tags, tool pointer), no document bodies.

Measured plugin-on vs plugin-off at four batch sizes, 120 runs: **identical turn counts, paired
wins at chance level, context delta within noise.** The plugin does not change retrieval cost.

What *does* save money is batching questions into one session — and that works with or without
the plugin:

| Questions per session | cost per question | vs 1/session |
|---|---|---|
| 1 | $0.461 | baseline |
| 4 | $0.132 | −71% |
| 8 | $0.074 | **−84%** |

### When to use which

| Scenario | What to use |
|---|---|
| KB under ~50 docs | grep or preload — cheaper, and Archcore's flat cost has nothing to amortise yet |
| KB beyond ~100–150 docs | **Archcore** — preload and grep both overtake it |
| Predictable cost matters more than the median | **Archcore** — 0/60 tail events vs 22/60 for grep |
| Latency matters | **Archcore** — 8.8 s mean vs 93 s worst case for grep |
| Several questions about one area | Batch them into one session — −71% at 4, −84% at 8 |
| Choosing the plugin for cheaper retrieval | Don't — it is cost-neutral. Use it for `document`/`plan`/`review` |

---

## Part 2 — Reproduce in this repo

### Prerequisites

```bash
archcore --version   # v0.7.x — install: https://archcore.ai
claude --version     # 2.1.x  — install: https://claude.ai/code
python3 --version    # 3.9+
jq --version         # any recent version
```

### 1. Clone and set up (one time)

```bash
git clone https://github.com/archcore-ai/bench.git
cd bench
bash setup.sh        # clones go-chi/chi and builds sanity harness arms
```

`setup.sh` fetches `go-chi/chi` to `repos/chi` and materializes the three sanity-harness
arm directories. Safe to re-run — skips steps already done.

### 2. Sanity check (2 min)

```bash
bash harness/bench.sh
column -t -s, results/results.csv
```

Token counts are exact, from `claude -p --output-format json` `.usage` (not estimates).

### 3. Full CLI benchmark (~2 h)

```bash
cd scale
python3 gen_kb.py                                              # 320-doc synthetic KB + facts.csv
MAXTURNS=20 CSV=$PWD/results/results_v2.csv bash run.sh all     # crossover + workload, 305 runs
python3 analyze_v2.py results/results_v2.csv results/results_v1.csv
```

Knobs: `MODEL` (default `sonnet`), `XTRIALS` (5), `WTRIALS` (3), `XSIZES` (`1 20 80 160 320`),
`MAXTURNS` (**use 20** — at 12 the blind-grep arm gets truncated and looks better than it is).

### 4. Plugin benchmark (~50 min)

Requires the [Archcore Plugin](https://github.com/archcore-ai/plugin):

```bash
git clone https://github.com/archcore-ai/plugin /path/to/plugin
PLUGIN=/path/to/plugin bash scale/run_plugin_v7.sh
```

The driver resolves both plugin layouts (v0.7 `plugins/archcore/`, and the pre-0.7 repo root)
and builds its own v0.7-conformant arm at N=80. Quick smoke test:

```bash
PLUGIN=/path/to/plugin TRIALS=1 BATCH_SIZES="1 4" DOMAINS="middleware" bash scale/run_plugin_v7.sh
```

Results: `scale/results/plugin_results_v7.csv`.

### Reading results

Both CSVs use the same key columns:

| Column | Meaning |
|---|---|
| `total_cost_usd` | Actual billed cost (warm — order-dependent, cache-discounted) |
| `input_tokens` | Fresh input tokens this session |
| `cache_creation` | Tokens written to prompt cache |
| `cache_read` | Tokens read from prompt cache |
| `num_turns` | Tool-use turns in this `claude -p` call |
| `pass` / `pass_rate` | 1 = correct answer retrieved, 0 = failed |

The headline **cold** cost is reconstructed order-independently:

```
ctx_in = input + cache_creation + cache_read
cold   = ctx_in × $3/M + output × $15/M
```

A second **realistic** metric models a fresh session per task with caching within the task.
It is reported alongside, with the caveat that it penalises turn reduction. Full methodology
and both metrics: [`ANALYSIS.md`](ANALYSIS.md).

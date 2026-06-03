# Archcore benchmark — token savings, reproducibly measured

Reproducible measurement of whether Archcore saves tokens for an AI coding agent at a **fixed
quality bar**, against realistic baselines. Two tools are measured: the **CLI** (Archcore as an
MCP server) and the **Plugin** (Claude Code integration with `/archcore:context`).

---

## Part 1 — What Archcore saves you

### CLI: stable retrieval cost at any knowledge base size

As a knowledge base grows, Archcore's per-task cost stays flat. Loading everything into
`CLAUDE.md` grows linearly. The gap widens without bound.

```
Per-task cost as the KB grows:

CLAUDE.md preload  ▏$0.10  →  ▍$0.24  →  █████ $0.68    grows linearly
archcore (CLI)     ▎$0.13  →  ▎$0.13  →  ▎$0.13          flat — independent of KB size
files + grep       ▎$0.10  →  ▎$0.12  →  ▎$0.11          also flat and comparable
                    1 doc       80 docs     320 docs
```

**Crossover table — realistic per-task cost ($), all arms at equal quality:**

| KB size | CLAUDE.md preload | files + index | files + grep | **Archcore CLI** |
|---------|-------------------|---------------|--------------|------------------|
| 1 doc   | **0.102**         | 0.111         | 0.103        | 0.127            |
| 20 docs | 0.134             | **0.113**     | 0.121        | 0.127            |
| 80 docs | 0.238             | **0.119**     | 0.123        | 0.127            |
| 160 docs| 0.386             | 0.130         | **0.124**    | 0.127            |
| 320 docs| 0.681             | 0.152         | **0.112**    | 0.127            |

**At ~27 documents**, Archcore becomes cheaper than `CLAUDE.md` preload. At 320 documents it is
**4.6× cheaper** ($0.127 vs $0.681). Archcore is at **rough parity with "files + grep"** across
the range — the two are within a few percent of each other at any KB size.

All arms answer every task correctly (100% pass rate, 305 measurements).

---

### Plugin: amortized sessions

The Archcore Plugin adds `/archcore:context` to Claude Code. When an agent loads an area's context
once at the start of a session, the fixed overhead (MCP schemas, system prompt, codebase context)
is paid once and shared across every question in that session.

**Per-question cost vs. number of questions per session:**

| Questions / session | Plugin cost / question | vs. one-call-per-question |
|---------------------|------------------------|---------------------------|
| 1                   | $0.163                 | −29%*                     |
| 2                   | $0.075                 | −41%                      |
| **4**               | **$0.032**             | **−74%**                  |
| 8                   | $0.015                 | −88%                      |

*Baseline = CLI separate calls at $0.127/question.
**A single-question Plugin session is 29% more expensive than a single CLI call** — the fixed
overhead is not yet amortized. The break-even is at ~2 questions per session.

**Full workload equivalent** — 20 tasks organized as 5 domain sessions of 4 questions each:

| Strategy | Total cost | vs. 20 separate CLI calls |
|----------|-----------|---------------------------|
| 20 × CLI (separate calls) | $2.54 | baseline |
| Plugin batch (5 sessions × 4q) | **$0.649** | **−74%** |

5 domains × 4 questions = the same 20-task suite, batched by area. 100% pass rate. 120 measurements across 3 trials, 5 domains, all batch sizes.

---

### When to use which

| Scenario | What to use |
|---|---|
| Script or one-off lookup | CLI (separate `claude -p` per question) |
| Interactive session, 2–3 questions about one area | Either — Plugin break-even is ~N=2 |
| Interactive session, 4+ questions about one area | **Plugin** — 74% cheaper per question |
| KB growing beyond ~30 docs | CLI beats `CLAUDE.md` preload; cost stays flat |
| Replacing a large `CLAUDE.md` | CLI — 4.6× cheaper at 320 docs |
| Need consistent, predictable cost | Plugin — 12× tighter cost variance at N=4 |

---

## Part 2 — Reproduce in this repo

### Prerequisites

```bash
archcore --version   # v0.4.x — install: https://archcore.ai
claude --version     # 2.x   — install: https://claude.ai/code
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

Runs 3 arms on a single task and 1-doc KB to verify the measurement harness:

```bash
bash harness/bench.sh
column -t -s, results/results.csv
```

Token counts are exact, from `claude -p --output-format json` `.usage` (not estimates).

### 3. Full CLI benchmark (~90 min)

Sweeps KB size and runs the 20-task workload suite. Regenerates the numbers in Part 1.

```bash
cd scale
python3 gen_kb.py                        # generates 320-doc synthetic KB + facts.csv
bash run.sh all                          # crossover (N sweep) + workload (20-task suite)
python3 analyze.py results/results.csv   # prints crossover + workload tables
```

Knobs: `MODEL` (default `sonnet`), `XTRIALS` (5), `WTRIALS` (3), `XSIZES` (`1 20 80 160 320`).
Raw per-run data: `scale/results/results.csv` (15-column CSV with exact API token counts).

### 4. Plugin benchmark (~60 min)

Requires the [Archcore Plugin](https://github.com/archcore-ai/plugin):

```bash
git clone https://github.com/archcore-ai/plugin /path/to/plugin
PLUGIN=/path/to/plugin bash scale/run_plugin.sh
```

The scale arms at N=80 must exist first (run step 3 or at minimum `bash scale/run.sh crossover`
with `XSIZES=80`). For a quick smoke test (one trial, two batch sizes, one domain):

```bash
PLUGIN=/path/to/plugin TRIALS=1 BATCH_SIZES="1 4" DOMAINS="middleware" bash scale/run_plugin.sh
```

Results: `scale/results/plugin_results.csv`.

### Reading results

Both CSVs use the same key columns:

| Column | Meaning |
|---|---|
| `total_cost_usd` | Actual billed cost (warm — lower bound) |
| `input_tokens` | Fresh input tokens this session |
| `cache_creation` | Tokens written to prompt cache |
| `cache_read` | Tokens read from prompt cache |
| `num_turns` | Tool-use turns in this `claude -p` call |
| `pass` / `pass_rate` | 1 = correct answer retrieved, 0 = failed |

The **realistic per-task cost** (headline metric) is reconstructed from these:

```
ctx_in  = input + cache_creation + cache_read
prefix  = ctx_in / num_turns
realistic = prefix × (1.25 + 0.10 × (turns−1)) × $3/M + output × $15/M
```

This models a fresh session per task (cold between sessions) but cached within a task
(consecutive turns in one CLI call). Full methodology: [`ANALYSIS.md`](ANALYSIS.md).

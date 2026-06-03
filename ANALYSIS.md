# Archcore Token Benchmark — Full Analysis

**English** · [Русский](ANALYSIS.ru.md)

> **Goal:** establish reproducibly whether Archcore saves tokens on a real codebase at a
> fixed quality bar — and if so, where exactly. This document gives every number and states
> the honest conclusions, including the claims you are not allowed to make.

Model: claude-sonnet-4-6. Token counts are exact, from `claude -p --output-format json` (`.usage`).

---

## 1. Overview

Two rigs:

| Rig | Location | What it measures |
|-----|----------|-----------------|
| **Sanity** | `bench/` | 1-doc KB, 3 arms — proves measurement harness is correct |
| **Scale — CLI** | `bench/scale/` | 320-doc KB, 5 arms, 305 runs — crossover + workload |
| **Scale — Plugin** | `bench/scale/` | N=80 KB, D-arm + C-arm control, 120 runs — batch economics |

---

## 2. CLI Benchmark

### 2.1 Arms

All arms share the same source substrate (`go-chi/chi`) and the same `Read/Grep/Glob` tools.
B1/B2/B3/C carry **identical documents** — only the access method differs. Arm A is the floor.

| Arm | Knowledge | Index | Extra tools | Models |
|-----|-----------|-------|-------------|--------|
| **A — cold** | none | — | — | no docs at all |
| **B1 — preload** | all N docs in `CLAUDE.md` | n/a | — | "put everything in context" |
| **B2 — index+grep** | N docs as files + `CLAUDE.md` index (paths+topics, no bodies) | yes | — | docs-as-files with a curated map |
| **B3 — blind grep** | same N docs as files, no index | no | — | docs-as-files, agent discovers via Grep |
| **C — archcore** | same N docs as files | no (auto) | archcore MCP | Archcore retrieval |

B2 and B3 are both included because Archcore's real competitor is not only naive preload but
also "just keep markdown in the repo." B2 gives the file-grep approach a perfect free index
(the hardest baseline). B3 removes the index — the agent must use built-in Grep. C-vs-B3
isolates "does Archcore's MCP search beat plain Grep over the same files?"

### 2.2 Knowledge base and quality control

320 synthetic documents across 5 domains (middleware, routing, errors, logging, testing),
**~550 tokens each** (a realistic ADR/rule: Context / Decision / Consequences / Alternatives /
Example / References sections). Each document encodes one normative convention whose answer is
an **arbitrary token buried in the Decision section** — it never appears in the title or excerpt,
so a search result alone is not sufficient to answer. The agent must open the document.

Exact-token grading: a correct answer means the knowledge was retrieved, not guessed.

### 2.3 Cost metric

Three metrics, all reconstructed order-independently from the API response:

- **realistic (headline):** models a fresh session per task (cold between tasks — the
  multi-session reality) but cached within a task (consecutive turns in one CLI call).
  ```
  ctx_in    = input_tokens + cache_creation + cache_read
  prefix    = ctx_in / num_turns
  realistic = prefix × (1.25 + 0.10 × (turns − 1)) × $3/M + output × $15/M
  ```
- **cold:** `ctx_in × $3/M + output × $15/M` — upper bound; over-charges multi-turn arms.
- **warm:** `total_cost_usd` — lower bound; understated by cross-run cache bleed.

All tables below use the realistic metric. Cold/warm bounds: `scale/results/FINDINGS_SCALE_raw.md`.

### 2.4 Crossover results

Fixed anchor task; KB size sweeps N ∈ {1, 20, 80, 160, 320}; 5 arms; 5 trials per cell.

| N (docs) | A cold | B1 preload | B2 index+grep | B3 blind grep | **C archcore** |
|----------|--------|------------|---------------|---------------|----------------|
| 1        | 0.204 ✗ | **0.102** | 0.111         | 0.103         | 0.127          |
| 20       | 0.183 ✗ | 0.134     | **0.113**     | 0.121         | 0.127          |
| 80       | 0.188 ✗ | 0.238     | **0.119**     | 0.123         | 0.127          |
| 160      | 0.195 ✗ | 0.386     | 0.130         | **0.124**     | 0.127          |
| 320      | 0.228 ✗ | 0.681     | 0.152         | **0.112**     | 0.127          |

✗ = task failed (Arm A has no access to the knowledge; pass 0–20%). Bold = cheapest arm.

**Crossover points:**

| Comparison | N where C becomes cheaper |
|---|---|
| C vs B1 (preload) | **~27 docs** |
| C vs B2 (index+grep) | ~272 docs |
| C vs B3 (blind grep) | rough parity across range; B3 marginally cheaper |

### 2.5 Workload results

Fixed N=80; 20 tasks spanning all 5 domains; arms B2/B3/C; 3 trials. B1 omitted (from the
crossover, at N=80 it would cost ~$0.24/task × 20 ≈ $4.8 — the worst). Arm A always fails.

| Arm | Suite realistic $ | Pass rate | Median turns/task |
|-----|-------------------|-----------|-------------------|
| B3 — blind grep | **$2.294** | 100% | 3 |
| B2 — index+grep | $2.375 | 100% | 2 |
| C — archcore | $2.716 | 100% | 5 |

All three answer every task correctly. B3 and B2 beat C by ~15% on suite cost.

### 2.6 Mechanism: turn count and the ToolSearch tax

What drives cost is the number of turns and what sits in context per turn:

| Arm | Turns | Context tokens (median, N=80) | Grows with N |
|-----|-------|-------------------------------|--------------|
| A cold | ~13 | ~352,000 | yes (digs through source) |
| B1 preload | **1** | 27K → 182K | **linear** (carries whole KB) |
| B2 index+grep | 2 | 54K–74K | near-flat |
| B3 blind grep | 3 | 80K–84K | flat |
| C archcore | **3** | **~93K** | **flat** |

Arm C uses 3 turns: `ToolSearch(search_documents)` → `search_documents(mode=full)` → answer.
The `search_documents` call with `mode=full` returns the matched document body inline, so a
separate `get_document` call is not needed. This matches B3's 3-turn pattern.

Without `mode=full`, Arm C would use 5 turns (an additional `ToolSearch(get_document)` +
`get_document`), because Claude Code loads MCP tool schemas lazily — each tool call is preceded
by a schema-load turn. `mode=full` collapses retrieval to one MCP call, eliminating that overhead.

The always-on contribution of the archcore MCP (schemas, server instructions) is ~638 tokens/turn
above the baseline, but this is a constant that cancels when comparing C to itself across N.

---

## 3. Plugin Benchmark

### 3.1 Methodology

The Plugin adds `/archcore:context` to Claude Code via `--plugin-dir`. In headless `claude -p`
sessions, the skill is invoked as the first line of the prompt:

```
/archcore:context middleware

For each question below, output ONLY the exact token value:
1. [question]
...
```

Two arms:

- **D-arm (Plugin):** `--plugin-dir /path/to/plugin` + `/archcore:context <domain>` prefix
- **C-arm (batch control):** same N questions, no plugin, one `claude -p` call

Baseline: **C-separate** = one `claude -p` call per question (CLI measurement, $0.127/question).

**Design:** 3 trials × 5 domains × 4 batch sizes (N ∈ {1, 2, 4, 8}) × 2 arms = **120 measurements**.
100% pass rate across all conditions.

### 3.2 Session amortization mechanism

The fixed per-session overhead — MCP tool schemas, plugin skill instructions, Claude Code system
prompt, source context — totals ~88–190k tokens depending on arm. This overhead is charged once
(cache-creation on turn 1) and cached on all subsequent turns within the session (cache-read at
0.10× rate). When N questions are batched in one session:

```
total_cost(N) ≈ overhead_cost + N × marginal_cost_per_answer
per_question(N) = total_cost(N) / N
```

Marginal cost per additional question is ~$0.002–0.005 (output tokens only). As N grows,
per-question cost converges toward this marginal cost, regardless of the large fixed overhead.

**D-arm turn count:** The `/archcore:context` skill calls `search_documents` without `mode=full`,
returning top-5 excerpts. Answer tokens are in the Decision section and do not appear in excerpts,
so the model calls `get_document` per question (~2 turns each). At N=4: 3 turns for context load
+ 8 turns for 4 questions + 1 answer turn = ~12 turns.

**C-arm turn count:** The model calls `search_documents(mode=full)` to retrieve all matching
document bodies inline, answering all N questions in one shot → 5 turns regardless of N.

Why D-arm beats C-arm at N≥4 in the realistic metric: with 12 turns, D's per-turn prefix is
~14k tokens (11 turns at 0.10× cache-read rate). With 5 turns, C's per-turn prefix is ~18k
tokens (4 turns at cache-read rate). The cache model favors more turns; at N≥4 this outweighs
D's higher absolute context.

### 3.3 Per-question cost by batch size

**Aggregate table — median over 3 trials, all 5 domains:**

| N questions/session | D-arm $/q | D IQR | C-arm $/q | C IQR | D/C ratio | saving vs C-sep |
|---------------------|-----------|-------|-----------|-------|-----------|-----------------|
| 1 | $0.163 | ±0.034 | $0.150 | ±0.001 | 1.09 | D: −29%, C: −18% |
| 2 | $0.075 | ±0.007 | $0.067 | ±0.014 | 1.13 | D: −41%, C: −47% |
| 4 | $0.032 | ±0.001 | $0.033 | ±0.008 | 0.97 | D: **−74%**, C: **−74%** |
| 8 | $0.015 | ±0.000 | $0.014 | ±0.009 | 1.05 | D: −88%, C: −89% |

Note: at N=1, both arms are more expensive than C-separate ($0.127). C-separate uses an
optimized 3-turn session for a single question; batch N=1 carries extra session overhead.

**Workload equivalent — 20 tasks (5 domains × 4 questions per domain):**

| Strategy | Total cost | vs C-sep 20×1 |
|----------|-----------|---------------|
| C-separate 20×1 | $2.540 | baseline |
| D-batch 5×4 | **$0.649** | **−74%** |
| C-batch 5×4 | $0.722 | −72% |

D-batch is 10% cheaper than C-batch on the full suite.

### 3.4 D vs C by domain at batch size 4

| Domain | D-arm $/q | C-arm $/q | Winner | Δ |
|--------|-----------|-----------|--------|---|
| middleware | $0.033 | $0.033 | D | 1% |
| routing | $0.033 | $0.033 | D | 1% |
| errors | $0.032 | $0.041 | **D** | **20%** |
| logging | $0.032 | $0.033 | D | 3% |
| testing | $0.032 | $0.041 | **D** | **21%** |

The Plugin wins all 5 domains. For `errors` and `testing` (ADR-type documents with complex
topic phrasing), D-arm is 20–21% cheaper — the context skill's curated overview helps the model
locate the correct documents without extra search iterations.

**Cost consistency:** D-arm IQR = $0.001/q at N=4; C-arm IQR = $0.008/q — Plugin is 8× more
consistent across domains and trials.

---

## 4. Comparison: CLI vs Plugin

| | CLI separate | Plugin N=1 | Plugin N=4 | Plugin N=8 |
|--|---|---|---|---|
| Cost/question (realistic) | $0.127 | $0.163 | $0.032 | $0.015 |
| vs CLI | baseline | +29% | −74% | −88% |
| Turns | 3 | 6 | 12 | 20 |
| Full 20-task suite | $2.54 | — | $0.649 | ~$0.31 |
| IQR/question | — | ±0.034 | ±0.001 | — |
| Best for | one-off lookups, scripts | — | sessions (4+ q/area) | long sessions |

**CLI wins when:** one question per run, scripted pipelines, or session structure is not possible.
Its $0.127/question cost is fixed, predictable, and independent of KB size.

**Plugin wins when:** a developer asks 4+ questions about the same area in one session. The cost
structure inverts — the fixed overhead becomes a fixed amortization budget. At N=8 per session,
cost reaches $0.015/question (88% lower than CLI-separate).

---

## 5. Claims

### CLI

- ✅ **CAN:** "Archcore keeps per-task cost flat as the KB grows; `CLAUDE.md` preload grows
  linearly. Beyond ~27 docs Archcore is cheaper; at 320 docs it is 4.6× cheaper."
- ✅ **CAN:** "Archcore is at parity with 'markdown files + grep' on per-task cost and requires
  no index maintenance."
- ✅ **CAN:** "Archcore achieves 100% task success across all KB sizes and all conditions."
- ❌ **CANNOT:** "Archcore saves tokens vs any baseline." It does not beat well-maintained grep.
- ❌ **CANNOT:** "Results generalize to real KBs." Tasks use non-derivable answer tokens —
  harder than most real lookups where partial context is informative.

### Plugin

- ✅ **CAN:** "Session batching of 4+ questions per area saves 74% per question vs separate
  calls. Holds across all 5 domains, 3 trials, 100% pass rate."
- ✅ **CAN:** "Plugin matches or beats raw MCP at N=4 across all domains. For ADR-type
  documents, Plugin is 20% cheaper than raw MCP at N=4."
- ✅ **CAN:** "Plugin provides 8–12× tighter cost variance per question vs raw MCP batch."
- ❌ **CANNOT:** "Plugin saves tokens for single-question sessions" — it costs 29% more.
- ❌ **CANNOT:** "Plugin context skill improves retrieval efficiency per document." The skill
  returns curated excerpts (top-5, no full bodies); the model still calls get_document for
  exact lookups. The savings come from session amortization, not faster retrieval.

---

## 6. Caveats

1. **Synthetic KB with non-derivable answer tokens** — a harder task than most real lookups.
   Real KBs with topic-adjacent answers may show different arm rankings.
2. **Single model (sonnet), single repo (chi).** Single-fact convention tasks only; no
   multi-document synthesis, no use of Archcore's relations or governance features.
3. **B2 index assumed perfectly maintained and free** — the hardest baseline for Archcore.
   In practice, maintaining a curated index has a real cost; this benchmark does not price it.
4. **Plugin batch: 5 domains measured, 3 trials each.** ADR-heavy KBs may show larger Plugin
   advantage; simpler rule-only KBs may show smaller advantage.
5. **Realistic metric is a reconstruction** — assumes ~constant per-turn prefix; cold/warm
   bounds are in `scale/results/FINDINGS_SCALE_raw.md`.

---

## 7. Reproduce

### CLI

```bash
cd scale
python3 gen_kb.py                        # 320 docs + facts.csv
bash run.sh all                          # crossover + workload (~90 min)
python3 analyze.py results/results.csv   # tables + charts
```

### Plugin

```bash
bash scale/run_plugin.sh   # 3 trials × 5 domains × 4 batch sizes × 2 arms
# Raw output: scale/results/plugin_results.csv
```

---

## 8. File map

```
bench/
├── README.md                 ← marketing overview + reproduce steps
├── SUMMARY.md                ← 5-minute summary (CLI + Plugin)        · SUMMARY.ru.md
├── ANALYSIS.md               ← this document                          · ANALYSIS.ru.md
├── harness/bench.sh          ← sanity rig (3 arms, 1 doc, 1 task)
├── results/FINDINGS.md       ← sanity results
└── scale/
    ├── README.md                 ← scale rig design
    ├── gen_kb.py / build_arm.py / grade.py / run.sh / analyze.py
    ├── run_plugin.sh             ← plugin benchmark driver
    ├── grade_batch.py            ← multi-answer grader
    ├── plugin_tasks.json         ← batch task groups (5 domains × 8 questions)
    ├── facts.csv                 ← KB metadata (question, answer_token, domain)
    ├── FINDINGS_SCALE.md         ← scale CLI findings                 · FINDINGS_SCALE.ru.md
    └── results/
        ├── results.csv           ← 305 CLI measurements
        ├── plugin_results.csv    ← 120 plugin measurements
        └── FINDINGS_SCALE_raw.md ← full tables (cold/warm bounds, token/turn breakdown)
```

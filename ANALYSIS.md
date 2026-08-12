# Archcore Token Benchmark — Full Analysis

**English** · [Русский](ANALYSIS.ru.md)

> **Goal:** establish reproducibly whether Archcore saves tokens on a real codebase at a
> fixed quality bar — and if so, where exactly. This document gives every number and states
> the honest conclusions, including the claims you are not allowed to make.

Model: **claude-sonnet-5** (`--model sonnet`). Token counts are exact, from
`claude -p --output-format json` (`.usage`).

**Measured 2026-08-12** — archcore CLI **v0.7.0**, plugin **v0.7.1**, Claude Code **2.1.228**.
Superseded run v1 (2026-05-31): archcore v0.3.6, plugin v0.6.x, Claude Code 2.1.16x, same model.
Both runs are in the repo (`results_v1.csv` / `results_v2.csv`); every table below shows v1 → v2.

---

## Verdict

### What was measured

One thing: how many tokens an agent spends finding a fact in the project's documentation.
Answer quality was not measured. Every access method answers equally correctly, which is built
into the task design so that cost can be compared at equal results. This benchmark says nothing
about whether Archcore makes answers better.

### What moves the bill most

| Change | Cost multiple | In dollars |
|---|---|---|
| Ask 8 questions in one session instead of 8 separate ones | **6.2×** | $0.462 → $0.074 per question |
| Stop keeping all documentation in `CLAUDE.md` (1 doc vs 320) | 5.6× | $0.139 → $0.784 per task |
| Switch to the cheapest search method (at 80 documents) | **1.3×** | $0.608 → $0.470 per task |

The search method is the weakest of the three. Start with the rows above it.

Batching was measured on Archcore only; the other methods were not run under batching. The
mechanism behind it is general: a fixed per-session overhead is divided across the questions in
that session.

### Should you adopt Archcore to save money

| Your situation | Answer |
|---|---|
| Fewer than 50 documents | No. `CLAUDE.md` or plain grep costs less. |
| More than 100 to 150 documents | Yes. Cheaper than every other method. |
| Somewhere in between | The difference is inside the margin of error. |
| The worst case hurts more than the typical case | Yes, from 80 documents up. The only method that never blew up: 0 spikes in 60 runs against 22 for grep. |
| Response time matters | Yes. 8.8 s on average against 16.3 s for grep, and 16.5 s at worst against 93 s. |

On the typical task grep costs 2.5× less ($0.178 against $0.437). On the average task Archcore
costs 23% less ($0.470 against $0.608). Both figures are correct and come from the same 60 runs.
Grep finds the file immediately in two cases out of three, and in the rest it fans out into a long
search that costs up to $2.40 per task.

### Did v0.7 make Archcore cheaper

No. It processed 142k tokens in May and 144k now, at $0.432 and $0.437. `mode=full` cut the number
of round trips from 5 to 3 and removed 33% of the waiting time, but not the tokens.

Its rank did change: in May it was the most expensive method, now it is the cheapest. The reason
lies elsewhere. Claude Code 2.1.228 regressed `Grep` and `Read` on large knowledge bases, and the
competing methods got 2.4× to 3.5× more expensive.

### Does the plugin reduce cost

No. Across all four batch sizes the number of round trips is identical and the price difference is
at chance level. The plugin exists for the `document`, `plan`, and `review` commands, not to make
search cheaper.

---

## 0. What changed since v1

Three things moved at once, and only one of them is Archcore.

| # | Change | Effect on the numbers |
|---|--------|-----------------------|
| 1 | **`search_documents(mode=full)` shipped** in CLI v0.7.0 | Arm C: 5 turns → **3 turns**. Token cost unchanged. Latency −33%. |
| 2 | **`/archcore:context` was removed** in plugin v0.7 | The entire v1 Plugin benchmark measured a mechanism that no longer exists. Rebuilt from scratch — §3. |
| 3 | **Claude Code 2.1.228 regressed Grep/Read on large KBs** | Baselines B2/B3 got 2.4–3.5× more expensive and became bimodal. **Not an Archcore improvement.** |

The headline ranking flips between v1 and v2 — Archcore goes from most-expensive to
cheapest on the workload suite. **Change #3 is the cause, not changes #1 or #2.** Archcore's
own cost did not move: arm C processed 142k context tokens in v1 and 144k in v2.

---

## 1. Overview

| Rig | Location | What it measures | Runs |
|-----|----------|-----------------|------|
| **Sanity** | `bench/` | 1-doc KB, 3 arms — proves the harness is correct | — |
| **Scale — CLI** | `bench/scale/` | 320-doc KB, 5 arms — crossover + workload | 305 |
| **Scale — Plugin** | `bench/scale/` | N=80 KB, D-arm + C-arm control — v0.7 session context | 120 |

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

Two metrics, both reconstructed order-independently from the API response. **Every conclusion
below is checked against both**; where they disagree, that is stated explicitly.

- **cold:** `ctx_in × $3/M + output × $15/M`, where `ctx_in = input + cache_creation + cache_read`.
  No turn model, no assumptions. Equals what an uncached session bills — every agent turn
  re-sends the full context as fresh input. Models the multi-session regime.
- **realistic:** models a fresh session per task, cached within the task.
  ```
  prefix    = ctx_in / num_turns
  realistic = prefix × (1.25 + 0.10 × (turns − 1)) × $3/M + output × $15/M
  ```

> **Caveat added in v2 — the realistic metric penalises turn reduction.** With `ctx_in` held
> constant, *fewer* turns scores as *more* expensive: the formula assumes context is spread
> across turns and discounted at cache-read rates. When `mode=full` cut arm C from 5 turns to
> 3 at identical token volume, C's realistic cost rose $0.147 → $0.212 while its cold cost was
> flat ($0.432 → $0.437). That is a modelling artifact, not a price increase. Prefer the cold
> metric when comparing arms whose turn counts differ a lot.

**Median vs mean.** v1 reported medians. In v2 the grep arms became bimodal (§2.6), and a
median hides exactly the behaviour that decides what a suite costs. Both are reported; the
mean is the number that lands on the invoice.

### 2.4 Crossover results

Fixed anchor task; KB size sweeps N ∈ {1, 20, 80, 160, 320}; 5 arms; 5 trials per cell.

**cold $/task — median (v1 → v2):**

| N | A cold | B1 preload | B2 index+grep | B3 blind grep | **C archcore** |
|---|--------|------------|---------------|---------------|----------------|
| 1 | 0.832 → 0.458 ✗ | 0.081 → **0.139** | 0.164 → 0.569 | 0.244 → 0.174 | 0.433 → 0.434 |
| 20 | 0.884 → 0.312 ✗ | 0.107 → **0.175** | 0.166 → 0.427 | 0.246 → 0.177 | 0.432 → 0.434 |
| 80 | 0.857 → 0.443 ✗ | 0.190 → 0.290 | 0.175 → 0.297 | 0.252 → **0.184** | 0.432 → 0.441 |
| 160 | 0.795 → 0.438 ✗ | 0.309 → 0.455 | 0.191 → 0.648 | 0.254 → 1.298 | 0.355 → **0.441** |
| 320 | 1.078 → 0.591 ✗ | 0.545 → 0.784 | 0.224 → 0.741 | 0.254 → 1.350 | 0.432 → **0.435** |

✗ = task failed (arm A has no access to the knowledge; pass 0/25). Bold = cheapest passing arm.

**Arm C is flat and deterministic.** Across all 25 crossover runs it used **exactly 3 turns**
and 143–146k context tokens — every trial, every KB size. No other arm is stable:

| Arm | Context tokens per trial (k), N=160 | N=320 |
|-----|-------------------------------------|-------|
| **C archcore** | `143, 144, 146, 146, 146` | `143, 143, 144, 144, 146` |
| B1 preload | `152, 152, 152, 152, 152` | `261, 261, 261, 261, 261` |
| B2 index+grep | `213, 213, 213, 264, 335` | `121, 244, 245, 304` |
| B3 blind grep | `51, 60, 424, 555, 919` | `50, 109, 438, 561, 831` |

B1 is stable too — it is preload, so its cost is deterministic by construction, and linear in N.

**Crossover points — N where C becomes cheaper:**

| Comparison | cold metric | realistic metric |
|---|---|---|
| C vs B1 (preload) | N ≈ 151 | N ≈ 12 |
| C vs B2 (index+grep) | N ≈ 106 | N ≈ 95 |
| C vs B3 (blind grep) | N ≈ 94 | N ≈ 86 |

The two metrics disagree sharply on B1 (12 vs 151) because B1 answers in one turn and C in
three — precisely the case where the turn model dominates. Quote the range, not one number.

**Context-window note.** v1 flagged preload overflow as a risk. On sonnet-5's 1M window it is
moot: B1 at 320 docs uses 261k tokens — 26% of the window. Preload's problem is now purely cost.

### 2.5 Workload results

Fixed N=80; 20 tasks spanning all 5 domains; arms B2/B3/C; 3 trials = 60 measurements per arm.

**Per-task cost distribution (v2, cold):**

| Arm | n | median | **mean** | min | max | max/med | runs >2× med | turns | pass |
|-----|---|--------|----------|-----|-----|---------|--------------|-------|------|
| B3 blind grep | 60 | **0.178** | 0.608 | 0.143 | 2.400 | 13.5× | **22/60** | 1 | 60/60 |
| B2 index+grep | 60 | 0.597 | 0.607 | 0.295 | 1.224 | 2.0× | 1/60 | 4 | 60/60 |
| **C archcore** | 60 | 0.437 | **0.470** | 0.433 | 0.635 | 1.5× | **0/60** | 3 | 60/60 |

**By median, blind grep is 2.5× cheaper than Archcore. By mean, Archcore is 23% cheaper than
both baselines.** Both statements are true; they describe the same 60 runs. The gap between
them is the tail.

**Suite total — cost to answer all 20 tasks once:**

| Arm | cold, v1 | cold, v2 median-based | **cold, v2 mean-based** | realistic, v2 mean-based |
|---|---|---|---|---|
| B2 index+grep | 3.50 | 11.95 | 12.14 | 4.72 |
| B3 blind grep | 5.04 | 3.56 | 12.17 | 5.05 |
| **C archcore** | 8.64 | 8.73 | **9.40** | **4.31** |

Median-based totals assume every task is the typical task — the assumption a bimodal arm
violates. **Under both metrics, on expected cost, arm C is the cheapest arm.** In v1 it was
the most expensive.

**Latency (seconds per task, v2):**

| Arm | median | mean | max |
|---|---|---|---|
| B3 blind grep | **2.6** | 16.3 | **93.4** |
| B2 index+grep | 12.3 | 12.6 | 26.8 |
| **C archcore** | 8.1 | **8.8** | **16.5** |

Same shape as cost: grep is fastest when it works and catastrophic when it doesn't.

### 2.6 Mechanism

**Why B3 blew up: it became bimodal.** Blind grep now resolves into two distinct populations:

| Population | Share | Context | cold $ | Duration |
|---|---|---|---|---|
| "lucky" (≤2 turns) | 65% | 50k | 0.151 | 2 s |
| "spiral" (>2 turns) | 35% | 438k | 1.338 | 32 s |

In v1 there was no such split — B3 delivered 83k tokens in 3 turns on essentially every run.
Under Claude Code 2.1.228 the agent either hits the right file immediately or fans out across
dozens of candidates. **B2 degraded the same way despite holding a perfect, free index** —
57k tokens/2 turns in v1 became 98–246k/2–5 turns at N=80. That an index-carrying arm regressed
is the clearest evidence the cause is host behaviour, not retrieval strategy.

**What `mode=full` actually bought.** Arm C, v1 → v2, workload:

| | turns | context | cold $ | duration | output |
|---|---|---|---|---|---|
| v1 (v0.3.6) | 5 | 142k | 0.432 | 12.0 s | 396 tok |
| v2 (v0.7.0) | **3** | 144k | 0.437 | **8.1 s** | 276 tok |

`search_documents(mode=full)` returns the matched body inline, removing the `get_document`
round-trip and one lazy-schema `ToolSearch` turn. It bought latency and turn count, not tokens:
the same context is processed either way.

**Baseline inflation is systemic.** B1 preload at N=1 went 27k → 46k context tokens; the
Claude Code system prompt grew roughly 19k tokens between 2.1.16x and 2.1.228. That is a
constant across arms and cancels in comparisons, but it means v1 and v2 absolute costs are
not directly comparable — only within-run rankings are.

**Methodology change: `MAXTURNS` 12 → 20.** In v1 no arm exceeded 12 turns. In v2, two B3 runs
needed 15 and 17, so a cap of 12 would have cut them short and understated B3's cost.

---

## 3. Plugin Benchmark

### 3.1 The v1 plugin benchmark measured a mechanism that no longer exists

Through plugin v0.6, the D-arm prompt opened with `/archcore:context <domain>` — an explicit
command that pulled an area's documents into the session up front. **Plugin v0.7 removed it.**
Commands are now `document` / `init` / `plan` / `review`, none of which retrieve.

Context now arrives a different way: a **SessionStart hook** injects a corpus header into every
session automatically — document counts, branch, tag vocabulary, and a pointer to the MCP tools.
Roughly 150 tokens, and **no document bodies**:

```
[Archcore — Git-native context for AI coding agents]
You have MCP tools available: list_documents, get_document, search_documents, ...
CORPUS: 80 documents — knowledge 80 · accepted 80
BRANCH: main
EXISTING TAGS: errors, logging, middleware, routing, testing, error, test, log, ...
```

This is a routing hint, not a preload. §3 was therefore rebuilt from scratch;
`scale/run_plugin.sh` is kept unchanged so the v1 numbers stay reproducible, and the new
driver is `scale/run_plugin_v7.sh`.

### 3.2 New design

- **D-arm:** `--plugin-dir …/plugins/archcore` → SessionStart injection + skills + hooks
- **C-arm:** no plugin, same archcore MCP server (control)
- **Both arms get an identical prompt.** In v0.7 the plugin's contribution is ambient rather
  than prompt-level, so any delta is attributable to it alone.

Verified before measuring: the hook does fire in headless `-p` mode (D quotes the `CORPUS`
line verbatim; C answers `NONE`), so the control is clean and no globally-installed plugin
leaks into C.

The KB is a v0.7-conformant copy of the N=80 arm — four uppercase acronym tags lowercased so
`archcore status` reports a clean project. All 80 fact tokens and all 40 plugin-task tokens
verified intact; the diff against the CLI arm is 8 tag lines. Retrieval difficulty is unchanged.

Design: 3 trials × 5 domains × 4 batch sizes (N ∈ {1,2,4,8}) × 2 arms = **120 measurements**,
0 errors, 100% pass rate.

### 3.3 Result: the plugin has no measurable effect on retrieval cost

| Batch | Arm | cold $/question (median) | mean | [min–max] | turns | context |
|---|---|---|---|---|---|---|
| 1 | C | 0.4606 | 0.4625 | [0.447–0.493] | 3 | 151k |
| 1 | **D** | 0.4594 | 0.4607 | [0.454–0.473] | 3 | 151k |
| 2 | C | 0.2313 | 0.2399 | [0.226–0.323] | 4 | 151k |
| 2 | **D** | 0.2382 | 0.2551 | [0.229–0.331] | 4 | 156k |
| 4 | C | 0.1257 | 0.1303 | [0.117–0.164] | 6 | 166k |
| 4 | **D** | 0.1277 | 0.1334 | [0.117–0.164] | 6 | 168k |
| 8 | C | 0.0834 | 0.0748 | [0.060–0.089] | 10 | 216k |
| 8 | **D** | 0.0653 | 0.0733 | [0.061–0.091] | 10 | 170k |

**Turn counts are identical at every batch size.** Paired by (domain, trial), D is cheaper in
8/15, 3/15, 7/15, 8/15 pairs at N = 1/2/4/8 — a coin flip, with the one deviation running
*against* the plugin. Paired median context delta is −82 / +2,444 / +73 / −11 tokens: at the
same order of magnitude as the ~150-token injection, i.e. indistinguishable from noise.

**The injected corpus header does not change how the model retrieves.** It announces what
exists; the model still runs the same search-and-read loop.

### 3.4 Session batching still works — but it was never the plugin's doing

| Questions/session | cold $/question (mean, both arms) | vs N=1 |
|---|---|---|
| 1 | 0.461 | baseline |
| 2 | 0.248 | −46% |
| 4 | 0.132 | −71% |
| 8 | 0.074 | **−84%** |

Fixed session overhead — MCP schemas, system prompt, source context — is charged once and
amortised across every question in the session. **Both arms get this equally.** In v1 this
saving was reported in the Plugin section and read as a plugin benefit; it is a property of
batching questions into one session, available with or without the plugin.

---

## 4. Comparison: CLI vs Plugin

| | CLI, 1 question/session | Batched, 4 q/session | Batched, 8 q/session |
|--|---|---|---|
| cold $/question | 0.461 | 0.132 | 0.074 |
| Turns | 3 | 6 | 10 |
| Plugin changes this? | no | no | no |

**Use batching when you can**: 4+ questions about one area in a single session is a 71–84%
per-question saving. **Load the plugin for what it now does** — `document` / `plan` / `review`
workflows and the authoring hooks — not for retrieval economics, where it is cost-neutral.

---

## 5. What the data shows, and what it does not

### Supported by the measurements

- Archcore's retrieval cost is flat and deterministic as the KB grows: 3 turns and 143–146k
  context tokens at every size from 1 to 320 documents, across 25 runs. This is the most
  strongly supported result here.
- On a 20-task suite at 80 documents, Archcore has the lowest expected cost of any method, 23%
  below both grep baselines, because it has no tail: 0 of 60 runs above 2× median against 22 of
  60 for blind grep. This holds under both cost metrics.
- Archcore answered every task correctly at every KB size and in every condition.
- `CLAUDE.md` preload grows linearly with KB size and Archcore does not. Past roughly 100 to 150
  documents Archcore is cheaper. The two metrics disagree on the exact point, so the range is
  the honest form of this statement (§2.4).
- Batching 4 to 8 questions about one area into a single session cuts per-question cost by 71%
  to 84%, across 120 measurements.

### Not supported

- **Archcore did not get cheaper in v0.7.** Its cost went from 142k to 144k tokens, $0.432 to
  $0.437. The ranking changed because the baselines regressed under Claude Code 2.1.228.
- **Archcore does not beat grep on the typical task.** By median, blind grep is 2.5× cheaper at
  80 documents. The Archcore advantage is in expected cost and in variance.
- **`mode=full` does not save tokens.** It saves a round trip and 33% of the latency at identical
  token volume.
- **The plugin does not reduce retrieval cost.** Four batch sizes, identical turn counts, paired
  wins at chance level, context delta within noise. The two v1 plugin claims (10% cheaper at
  N=4, tighter cost variance) described `/archcore:context`, which no longer exists.

### Out of scope entirely

- **Answer quality.** Every method that carries the knowledge answers correctly, by construction,
  so cost can be compared at equal results. Nothing here shows whether Archcore makes answers
  better, only what retrieval costs.
- **Multi-document reasoning, relations, drift, and governance.** All tasks are single-fact
  lookups. The features Archcore is mostly adopted for are not exercised.
- **Generalisation to real knowledge bases.** Answer tokens are deliberately non-derivable,
  which is harder than most real lookups, where partial context already helps.
- **Stability across host versions.** Every baseline comparison depends on Claude Code's
  Grep/Read behaviour, which changed materially inside one minor-version range.

---

## 6. Caveats

1. **Synthetic KB with non-derivable answer tokens** — a harder task than most real lookups.
   Real KBs with topic-adjacent answers may show different arm rankings.
2. **Single model (sonnet-5), single repo (chi).** Single-fact convention tasks only; no
   multi-document synthesis, no use of Archcore's relations or governance features.
3. **B2's index is assumed perfectly maintained and free** — the hardest baseline for Archcore.
   Maintaining a curated index has a real cost this benchmark does not price.
4. **Host-version sensitivity is now a first-order effect.** Between Claude Code 2.1.16x and
   2.1.228, the grep baselines changed cost by 2.4–3.5× with no change to the KB, the task, or
   the model. Treat every cross-arm number as valid for a stated host version only.
5. **5 trials per crossover cell is thin for bimodal arms.** The workload phase (60 per arm)
   is the reliable basis for distribution claims; the crossover phase is directional.
6. **The realistic metric penalises turn reduction** (§2.3) — prefer cold when turn counts differ.
7. **v1 and v2 absolute costs are not comparable** — the host system prompt grew ~19k tokens.
   Compare rankings within a run, not dollar figures across runs.

---

## 7. Reproduce

### CLI

```bash
cd scale
python3 gen_kb.py                                     # 320 docs + facts.csv
MAXTURNS=20 CSV=$PWD/results/results_v2.csv bash run.sh all      # ~2 h, 305 runs
python3 analyze_v2.py results/results_v2.csv results/results_v1.csv
```

### Plugin

```bash
PLUGIN=/path/to/plugin bash scale/run_plugin_v7.sh    # ~50 min, 120 runs
# Raw output: scale/results/plugin_results_v7.csv
```

`run_plugin_v7.sh` resolves both plugin layouts (v0.7 `plugins/archcore/`, and the pre-0.7
repo root) and builds its own v0.7-conformant arm.

---

## 8. File map

```
bench/
├── README.md                 ← overview + reproduce steps
├── SUMMARY.md                ← 5-minute summary                       · SUMMARY.ru.md
├── ANALYSIS.md               ← this document                          · ANALYSIS.ru.md
├── harness/bench.sh          ← sanity rig (3 arms, 1 doc, 1 task)
├── results/FINDINGS.md       ← sanity results
└── scale/
    ├── README.md                 ← scale rig design
    ├── gen_kb.py / build_arm.py / grade.py / run.sh
    ├── analyze.py                ← v1 analyzer (medians)
    ├── analyze_v2.py             ← v2 analyzer (median + mean + tail frequency)
    ├── run_plugin.sh             ← v1 plugin driver (/archcore:context — kept for reproducibility)
    ├── run_plugin_v7.sh          ← v2 plugin driver (SessionStart mechanism)
    ├── plugin_tasks.json         ← batch task groups (5 domains × 8 questions)
    ├── facts.csv                 ← KB metadata (question, answer_token, domain)
    └── results/
        ├── results_v1.csv        ← 305 CLI measurements (2026-05-31, archcore v0.3.6)
        ├── results_v2.csv        ← 305 CLI measurements (2026-08-12, archcore v0.7.0)
        ├── plugin_results.csv    ← 120 plugin measurements (v1 mechanism)
        └── plugin_results_v7.csv ← 120 plugin measurements (v0.7 mechanism)
```

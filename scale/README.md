# Archcore token benchmark — scale rig (crossover + workload)

Builds on the sanity rig (`../`) to answer the real question: **on a fixed-quality task,
where — if anywhere — does Archcore's on-demand retrieval actually cost fewer tokens than
the alternatives, as the knowledge base (KB) grows?**

The sanity run already showed that on a 1-doc KB, flat preload (CLAUDE.md) wins. This rig
scales the KB and measures the **crossover**, plus a realistic **workload** total.

## What this measures (and what it doesn't)

We measure **token cost at equal task success**. Quality is controlled by construction:
every task asks for a single *normative convention* whose answer is an **arbitrary token
buried in one doc** (e.g. "the route mount prefix for health-check endpoints is `/rte86y`").
The token is non-derivable from source, so an arm answers correctly **iff** it actually had
the fact (via preload or retrieval). A grader checks the exact token in the final answer.

This is a **retrieval-cost** benchmark. It deliberately does *not* test reasoning quality,
multi-doc synthesis, relations, drift, or governance — areas where Archcore's value is
structural rather than token-denominated.

## Arms (apples-to-apples)

All arms share the same chi source substrate and the same `Read/Grep/Glob` tools. They carry
**identical facts** (B1/B2/B3/C hold the same N docs); only *how the knowledge is accessed*
differs. Arm A is the floor (no docs).

| Arm | Knowledge | Index? | Tools | Models… |
|-----|-----------|--------|-------|---------|
| **A — cold** | none | — | Read/Grep/Glob | repo with no agent docs (floor) |
| **B1 — preload** | all N docs concatenated into `CLAUDE.md` | n/a | Read/Grep/Glob | "put everything in context" |
| **B2 — index+grep** | N docs as `.archcore/*.md` files + a maintained `CLAUDE.md` index (paths+topics, **no tokens**) | yes (hand-maintained) | Read/Grep/Glob | docs-as-files w/ a curated map |
| **B3 — blind grep** | same N docs as files, **no index** | no | Read/Grep/Glob | docs-as-files, agent discovers via Grep |
| **C — archcore** | same N docs as files | no (auto) | Read/Grep/Glob **+ archcore MCP** | Archcore |

Why B2 **and** B3: Archcore's real competitor isn't only naive preload — it's "just keep
markdown in the repo." B2 gives that approach a *perfect hand-maintained index* (the hardest
baseline). B3 removes the index so the agent must discover docs via the built-in Grep — the
fair head-to-head against Archcore's MCP search, since **both have zero index maintenance**.
C-vs-B3 isolates "does archcore's MCP retrieval beat plain Grep over the same files?"

## Two phases

- **Crossover** — one fixed task (anchor doc, present at every N); sweep `N ∈ {1,20,80,160,320}`;
  all 5 arms; 5 trials. Plots cost vs KB size → locates where preload's linear growth crosses
  retrieval's flat cost, and where preload exceeds the context window (`✗ovf`).
- **Workload** — fixed `N=80`; a 20-task suite spanning all 5 domains (one fact each); arms
  B2/B3/C; 3 trials. Reports the **suite total** = cost to answer the whole suite once.

## The prompt-cache confounder — bracketed, not fought

Prompt caching makes a preloaded `CLAUDE.md` ~free on a cache *hit*, but cache state also bleeds
across sequential `claude -p` runs, so raw billed cost is order-dependent. We handle this two ways:

1. **Randomized arm order** per unit (deterministic per seed) decorrelates cache state from arm.
2. **Two cost views**, reported side by side:
   - **cold-session cost** = `(input + cache_creation + cache_read) × $3/M + output × $15/M`.
     Order-independent. Equals what an *uncached* session would bill — every agent turn re-sends
     the full context as fresh input. Models the **multi-session** regime (separate sessions over
     days; cache cold each time) — Archcore's intended home turf.
   - **warm billed cost** = the actual `total_cost_usd` (cache-discounted). Models **one long
     session**; favors preload.

   The truth for a given team lives between the two. Cold is the headline because it's
   order-independent and reflects the multi-session reality.

Note the cold view exposes a real effect: retrieval needs a multi-turn loop, and each turn re-bills
context. Preload answers in one turn. So retrieval is not "free." Under Claude Code's **lazy
MCP-tool loading**, arm C's loop on archcore v0.3.6 was `ToolSearch(search) → search →
ToolSearch(get) → get → answer` = 5 turns — 2 of them (`ToolSearch`) schema-load overhead the
built-in Grep doesn't pay.

**Resolved in v0.7.0:** `search_documents(mode=full)` returns the matched body inline, dropping
`get_document` and one schema-load turn from the loop → **measured 3 turns, in all 25 crossover
runs**. What it bought is latency (12.0 s → 8.1 s per task, −33%) and turn count, **not tokens**:
context processed went 142k → 144k and cold cost $0.432 → $0.437. Do not claim a token saving
for `mode=full`.

**Also measured in v2: the `realistic` metric penalises turn reduction.** With `ctx_in` fixed,
fewer turns scores as more expensive (the formula assumes context is spread across turns at
cache-read rates). Arm C's realistic cost "rose" $0.147 → $0.212 on identical token volume.
Prefer the cold view when comparing arms whose turn counts differ a lot.

## Reproduce

```bash
python3 gen_kb.py                                                # NDOCS=320 → kb/ + facts.csv
MAXTURNS=20 CSV=$PWD/results/results_v2.csv bash run.sh all      # crossover + workload (~2 h)
python3 analyze_v2.py results/results_v2.csv results/results_v1.csv
```
Knobs: `MODEL` (default sonnet), `XSIZES`, `XTRIALS` (5), `WTRIALS` (3), `WSIZE` (80), `NDOCS`,
`MAXTURNS`.

**Use `MAXTURNS=20`, not the default 12.** On Claude Code 2.1.228 the blind-grep arm needs 15–17
turns on its worst runs; a cap of 12 truncates them, hides B3's tail, and flatters archcore.
No arm exceeded 12 turns on the 2026-05-31 run, which is why the old default was safe then.

Pins (current run, 2026-08-12): chi @ `3b171578`, **archcore v0.7.0**, plugin v0.7.1,
**claude 2.1.228**, model=sonnet (resolves to sonnet-5). Previous run 2026-05-31: archcore
v0.3.6, claude 2.1.16x, same model. Token counts are exact (`claude -p --output-format json`
`.usage`); cold-session priced at Sonnet list ($3/M in, $15/M out).

**Host-version sensitivity is a first-order effect.** Between those two Claude Code versions the
grep baselines changed cost by 2.4–3.5× with no change to the KB, task, or model, and became
bimodal (65% resolve in ≤2 turns / 35% spiral into 400k+ tokens). Arm C did not move (142k → 144k).
Treat every cross-arm number as valid for a stated host version only.

## Isolation

- `--strict-mcp-config --mcp-config <file>` controls MCP exactly (default headless loads the
  user's global MCP ≈ 40K tokens of noise; strict mode zeroes it). Arm C points archcore at its
  own per-N working copy; all others get an empty MCP config.
- Per-(N,arm) working-dir copies control `CLAUDE.md` / `.archcore/` presence.
- Default config dir retained (OAuth in macOS Keychain). Residual global-plugin skill frontmatter
  is a symmetric constant across arms and cancels in deltas.

## Honest design choices (so the numbers survive scrutiny)

- **Doc size is realistic (~550 tokens; a full ADR/rule: Context/Decision/Consequences/
  Alternatives/Example/References).** Tiny docs would understate preload cost and push the
  crossover off-chart. The generator prints the average size; it is auditable.
- **Answer tokens are buried below the search-matched text**, so arm C genuinely pays
  `get_document` (verified: search excerpt never leaks the token).
- **Task topics resolve to exactly one doc** (filler docs use a disjoint vocabulary), so
  retrieval cost — not disambiguation luck — is what's measured. Verified at N=320.
- **B2 gets the strongest possible (perfect, free) index** — the hardest baseline for Archcore.

## Known limitations

1. Single model (sonnet-5), single repo (chi). Convention-style single-fact tasks only.
2. `B2`'s index is assumed perfectly maintained and free; in reality maintaining it has a cost
   Archcore avoids — not captured here.
3. ~~The curated `/archcore:context` skill may be more turn-efficient but isn't exercisable
   cleanly in headless.~~ **Moot as of plugin v0.7:** the skill was removed. Session context is
   now injected by a SessionStart hook (~150-token corpus header, no document bodies) and was
   measured directly — 120 runs, no effect on retrieval cost. See `run_plugin_v7.sh`.
4. cold/warm bracket the cache effect but don't model intermediate session cadences.
5. 5 trials per crossover cell is thin now that two arms are bimodal. Distribution claims should
   rest on the workload phase (60 runs/arm); treat the crossover sweep as directional.

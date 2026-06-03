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
MCP-tool loading**, arm C's actual loop is `ToolSearch(search) → search → ToolSearch(get) → get →
answer` = 5 turns — 2 of them (`ToolSearch`) are schema-load overhead the built-in Grep doesn't pay
(verified post-hoc on CC 2.1.160; see `../rnd.md` and `../ANALYSIS.md` §3.4). A `mode=full` parameter
on `search_documents` (returns the matched body inline) drops `get_document` from the loop → measured
3 turns / $0.127, i.e. grep parity at equal quality (`../rnd.md` §9.4).

## Reproduce

```bash
python3 gen_kb.py            # NDOCS=320 by default → kb/ + facts.csv (prints avg doc size)
bash run.sh all              # crossover + workload → results/results.csv  (~80–100 min)
python3 analyze.py results/results.csv > results/FINDINGS_SCALE.md
```
Knobs: `MODEL` (default sonnet), `XSIZES`, `XTRIALS` (5), `WTRIALS` (3), `WSIZE` (80), `NDOCS`.

Pins: chi @ `3b171578`, archcore v0.3.6, claude 2.1.x, model=sonnet. Token counts are exact
(`claude -p --output-format json` `.usage`); cold-session priced at Sonnet list ($3/M in, $15/M out).

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

1. Single model (sonnet), single repo (chi). Convention-style single-fact tasks only.
2. `B2`'s index is assumed perfectly maintained and free; in reality maintaining it has a cost
   Archcore avoids — not captured here.
3. The bare agent drives the archcore MCP directly; the curated `/archcore:context` skill (one
   `search(limit=50)` → top-5) may be more turn-efficient but isn't exercisable cleanly in headless.
4. cold/warm bracket the cache effect but don't model intermediate session cadences.

---
title: "Benchmark methodology"
status: accepted
tags:
  - "benchmark"
  - "methodology"
  - "spec"
---

## Purpose

Normative specification for Archcore token-savings benchmarks. Any benchmark phase that claims comparability with v1 results MUST conform to every MUST-level requirement here.

## Scope

Covers: arm definitions, KB design invariants, cost metric formulas, grading, isolation requirements, and aggregation rules. Does not cover: harness implementation details, analysis scripts, or interpretation of results (see findings docs for those).

## Subject

Headless `claude -p` benchmark sessions measuring per-task and per-question token cost across alternative knowledge-access strategies: context preloading (B1), docs-as-files with index (B2), docs-as-files without index (B3), Archcore MCP retrieval (C), and Archcore Plugin batch sessions (D). Two instruments: CLI benchmark (`@scale/run.sh`) and Plugin benchmark (`@scale/run_plugin.sh`). All results in USD using Sonnet 4.x list pricing ($3/M input, $15/M output).

## Contract Surface

| Field | Required | Source |
|-------|----------|--------|
| `input_tokens` | MUST | API response `.usage` |
| `cache_creation` | MUST | API response `.usage` |
| `cache_read` | MUST | API response `.usage` |
| `output_tokens` | MUST | API response `.usage` |
| `total_cost_usd` | MUST | API response `.usage` |
| `num_turns` | MUST | API response tool-use turn count |
| `pass` | MUST | `@scale/grade.py` or `@scale/grade_batch.py` exact-match result |

## Normative Behavior

### CLI Benchmark: 5-Arm Design

A CLI benchmark run MUST include these five arms. Arms share the same source substrate (chi router) and Read/Grep/Glob tools.

| Arm | CLAUDE.md | `.archcore/` docs | MCP servers | Defines |
|-----|-----------|-------------------|-------------|---------|
| A — cold | none | none | none | Cost floor |
| B1 — preload | Full bodies of N docs concatenated (frontmatter stripped) | none | none | "dump everything" ceiling |
| B2 — index+grep | Index only: paths + topic, NO answer tokens | N docs present | none | Best-case markdown-in-repo |
| B3 — blind grep | none | N docs present | none | Markdown-in-repo without index maintenance |
| C — archcore | none | N docs present | archcore MCP | Archcore retrieval |

All B and C arms MUST carry identical doc files for a given N; only access method differs.

### CLI Phases

**Crossover phase**
- One fixed anchor task (same question across all N and all arms).
- KB sizes: N ∈ {1, 20, 80, 160, 320}.
- All 5 arms.
- Minimum 5 trials per (N, arm) cell.
- Purpose: locate the crossover point where retrieval cost ≤ preload cost.

**Workload phase**
- Fixed KB size N = 80.
- 20 tasks, one per KB doc, spanning all 5 domains (4 tasks per domain).
- Arms B2, B3, C only (A and B1 excluded — A fails, B1's per-task cost at N=80 is already known from crossover).
- Minimum 3 trials per (N, arm, task_id) cell.
- Purpose: measure total per-task cost across a realistic diverse task suite.

### Plugin Benchmark: 2-Arm Design

The Plugin benchmark measures session amortization economics. Two arms, both using the archcore MCP server:

| Arm | `--plugin-dir` | Prompt prefix | Strategy |
|-----|---------------|---------------|----------|
| C-batch | no | none | Raw MCP, N questions in one `claude -p` call |
| D — plugin | yes | `/archcore:context <domain>` as first line | Plugin skill + MCP, N questions batched |

**D-arm construction:** same working directory as C (chi source + `.archcore/` with N=80 docs, no CLAUDE.md). The `--plugin-dir` flag activates the `/archcore:context` skill. Each session prompt starts with `/archcore:context <domain>` followed by N questions.

**C-batch construction:** identical to C-arm but N questions are sent in one `claude -p` call rather than N separate calls. Baseline for comparison is C-separate ($0.127/question, 3 turns, from `@scale/results/results.csv` mode=full measurements).

### Plugin Phase

**Batch economics phase**
- Fixed KB size N = 80 (5 domains × 16 docs each).
- Batch sizes: N_q ∈ {1, 2, 4, 8} questions per session.
- Both arms (D and C-batch).
- Minimum 3 trials per (domain, arm, batch_size) cell.
- 5 domains: middleware, routing, errors, logging, testing.
- Total: 3 × 5 × 4 × 2 = 120 measurements.
- Purpose: measure per-question cost as session amortization benefit grows with batch size.

Questions within a batch MUST be drawn from `@scale/plugin_tasks.json` (same set across D and C-batch). Grading by `@scale/grade_batch.py` (exact-match, all N answers checked).

### Knowledge Base Design

The synthetic KB MUST preserve these honesty invariants:

1. **One normative convention per doc.** Each doc encodes exactly one fact; the answer is an arbitrary unique token (e.g. `mwg_a3b7`) not derivable from the question.
2. **Topic/token split.** The topic phrase appears ONLY in title + Context section. The answer token appears ONLY in Decision + Example sections. A grep on the topic returns a title/Context excerpt without the token — `get_document` or Read is genuinely required.
3. **Realistic doc size.** Each doc MUST be approximately 550 tokens (6 sections: Context / Decision / Consequences / Alternatives / Example / References). Preload cost MUST NOT be understated by using thin docs.
4. **Multi-domain prefix coverage.** Docs MUST be interleaved across domains by doc_id so that any prefix of size N spans all domains.
5. **Filler disjointness.** Docs beyond 16 per domain MUST use a vocabulary disjoint from the 16 base topic phrases so that a topic search returns exactly one result regardless of N.
6. **Exact-match grading.** The answer token MUST appear verbatim (case-insensitive substring) in the final agent response. A pass means the knowledge was retrieved, not guessed.

Five domains: `middleware` (type: rule), `routing` (type: rule), `errors` (type: adr), `logging` (type: rule), `testing` (type: rule). Doc files at `@scale/kb/<domain>/<slug>.<type>.md`. Fact metadata at `@scale/facts.csv` (columns: `doc_id, domain, type, path, title, topic, slot, question, answer_token, search_term`).

### Cost Metric

Three metrics computed per row from raw API fields: `input_tokens`, `cache_creation`, `cache_read`, `output_tokens`, `total_cost_usd`, `num_turns`. Let `ctx_in = input_tokens + cache_creation + cache_read`.

**Cold** (upper bound): `ctx_in × $3/M + output_tokens × $15/M` — over-charges multi-turn arms.

**Warm** (lower bound): `total_cost_usd` — understated when cross-run cache bleed is present.

**Realistic** (HEADLINE — MUST be primary):
`turns = max(1, num_turns); prefix = ctx_in / turns; realistic = prefix × (1.25 + 0.10 × (turns − 1)) × $3/M + output_tokens × $15/M`

For Plugin batch sessions: `per_question_realistic = realistic / N_q`.

Pricing basis: Sonnet 4.x — $3/M input, $15/M output.

### Aggregation Rules

- Group by `(phase, N, task_id, arm)` for CLI; by `(domain, arm, batch_size)` for Plugin.
- Report **median** over trials for: `realistic`, `cold`, `warm`, `ctx_in`, `num_turns`.
- Report **mean** over trials for: `pass_rate`, `err_rate`.
- Usable rows: `ctx_in > 1000`. Max-turns rows: keep (real cost).
- Workload totals: sum of per-task medians per arm.
- Plugin per-question cost: median realistic ÷ batch size N_q.

### Isolation Requirements

- MUST pass `--strict-mcp-config --mcp-config <file>` to every `claude -p` invocation.
- Arms C and D MUST use an MCP config activating archcore at the arm's working directory.
- Arms A / B1 / B2 / B3 / C-batch MUST use `{"mcpServers":{}}`.
- Each (N, arm) pair MUST have its own directory copy.
- D-arm MUST pass `--plugin-dir <path>` pointing to the archcore plugin directory.
- The user's default config dir (OAuth credentials) MUST be retained for authentication.

## Constraints

- Arms MUST NOT differ on the source substrate (same chi router, same file tree).
- The anchor task for crossover MUST be the same question for every (N, arm) cell and every trial.
- The answer token for each task MUST NOT appear in the chi source tree, filenames, or any CLAUDE.md index.
- Plugin batch questions MUST be identical across D and C-batch for the same (domain, batch_size, trial).

## Invariants

- For any N and arm: `cold ≥ realistic ≥ warm`.
- B1/B2/B3/C at the same N carry exactly the same set of doc files.
- Arm A cost is independent of N (no knowledge loaded).
- D-arm and C-batch carry the same `.archcore/` docs; only the plugin flag and prompt prefix differ.

## Error Handling

- Exclude rows with `ctx_in ≤ 1000`.
- Max-turns flailing: keep rows.
- Grading failures: `pass=0`; do not exclude from cost aggregation.
- Plugin batch: `pass=1` requires ALL N_q answers correct.

## Conformance

A benchmark phase is **conforming** if it satisfies all MUST-level requirements above. Non-conforming results MUST be labeled exploratory and MUST NOT be compared against v1 baseline numbers.

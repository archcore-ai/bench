---
title: "Benchmark methodology"
status: accepted
tags:
  - "benchmark"
  - "methodology"
  - "spec"
---

## Purpose

Normative specification for Archcore token-cost benchmarks. Any benchmark phase that claims
comparability with a prior run MUST conform to every MUST-level requirement here.

Revised 2026-08-12 after the v2 run. Changes from the v1 revision are marked **[v2]** and are
consequences of measurement, not preference: the plugin mechanism this spec previously mandated
was removed upstream, and two arms became bimodal, which invalidated median-only aggregation.

## Scope

Covers: arm definitions, KB design invariants, cost metric formulas, grading, isolation
requirements, and aggregation rules. Does not cover: harness implementation details, analysis
scripts, or interpretation of results (see findings docs).

## Subject

Headless `claude -p` benchmark sessions measuring per-task and per-question token cost across
alternative knowledge-access strategies: context preloading (B1), docs-as-files with index (B2),
docs-as-files without index (B3), Archcore MCP retrieval (C), and Archcore Plugin sessions (D).
Two instruments: CLI benchmark (`@scale/run.sh`) and Plugin benchmark (`@scale/run_plugin_v7.sh`).
Results in USD at Sonnet list pricing ($3/M input, $15/M output).

**[v2] Host and model MUST be recorded with every result set.** Between Claude Code 2.1.16x and
2.1.228 the grep baselines changed cost by 2.4-3.5x with no change to KB, task, or model. A
result set without a stated host version is not interpretable.

## Contract Surface

| Field | Required | Source |
|-------|----------|--------|
| `input_tokens` | MUST | API response `.usage` |
| `cache_creation` | MUST | API response `.usage` |
| `cache_read` | MUST | API response `.usage` |
| `output_tokens` | MUST | API response `.usage` |
| `total_cost_usd` | MUST | API response `.usage` |
| `num_turns` | MUST | API response tool-use turn count |
| `duration_ms` | MUST **[v2]** | wall clock around the `claude -p` call |
| `pass` | MUST | `@scale/grade.py` exact-match result |

## Normative Behavior

### CLI Benchmark: 5-Arm Design

A CLI benchmark run MUST include these five arms, sharing the same source substrate (chi router)
and Read/Grep/Glob tools.

| Arm | CLAUDE.md | `.archcore/` docs | MCP servers | Defines |
|-----|-----------|-------------------|-------------|---------|
| A - cold | none | none | none | Cost floor |
| B1 - preload | Full bodies of N docs concatenated | none | none | "dump everything" ceiling |
| B2 - index+grep | Index only: paths + topic, NO answer tokens | N docs present | none | Best-case markdown-in-repo |
| B3 - blind grep | none | N docs present | none | Markdown-in-repo without index maintenance |
| C - archcore | none | N docs present | archcore MCP | Archcore retrieval |

All B and C arms MUST carry identical doc files for a given N; only access method differs.

**[v2] `MAXTURNS` MUST be at least 20.** On CC 2.1.228 the B3 arm needs 15-17 turns on its worst
runs. A cap of 12 truncates those runs, hides B3's tail, and biases the comparison toward
Archcore. WHEN any run terminates at the turn cap, the analysis MUST report how many did.

### CLI Phases

**Crossover phase**
- One fixed anchor task (same question across all N and all arms).
- KB sizes: N in {1, 20, 80, 160, 320}. All 5 arms. Minimum 5 trials per (N, arm) cell.
- Purpose: locate the crossover point where retrieval cost <= preload cost.
- **[v2]** Directional only. 5 trials per cell is insufficient to characterise a bimodal arm;
  distribution claims MUST rest on the workload phase.

**Workload phase**
- Fixed KB size N = 80. 20 tasks spanning all 5 domains. Arms B2, B3, C.
- Minimum 3 trials per (N, arm, task_id) cell = 60 measurements per arm.
- Purpose: per-task cost distribution across a realistic diverse task suite.

### [v2] Plugin Benchmark: 2-Arm Design

The `/archcore:context` command was removed in plugin v0.7; the D-arm construction mandated by
the v1 revision of this spec is no longer executable. Session context now arrives via a
SessionStart hook that injects a corpus header (~150 tokens: document counts, branch, tag
vocabulary, tool pointer) and no document bodies.

| Arm | `--plugin-dir` | Prompt | Strategy |
|-----|---------------|--------|----------|
| C-batch | no | N questions | Raw MCP control |
| D - plugin | yes | N questions, **identical to C** | SessionStart injection + skills + hooks |

**Prompts MUST be identical across D and C.** In v0.7 the plugin's contribution is ambient
rather than prompt-level; a prompt difference would confound the only effect under test.

**The harness MUST verify the hook fires before measuring.** Probe both arms with a question
that asks the model to quote the injected corpus line. D MUST quote it; C MUST report none.
IF C also receives injected context, a globally installed plugin is leaking into the control
and the run MUST be discarded.

**The plugin path MUST be resolved, not assumed.** v0.7 restructured the repository into a
marketplace layout (`plugins/archcore/.claude-plugin/plugin.json`); earlier versions kept the
manifest at the repo root. `--plugin-dir` MUST point at the directory containing the manifest.

### Plugin Phase

- Fixed KB size N = 80. Batch sizes N_q in {1, 2, 4, 8}. Both arms.
- Minimum 3 trials per (domain, arm, batch_size) cell; 5 domains = 120 measurements.
- Questions MUST come from `@scale/plugin_tasks.json`, identical across arms for a given
  (domain, batch_size, trial). All N_q answers must be correct for `pass=1`.
- **[v2]** Comparison MUST be paired by (domain, trial), not pooled. Pooled medians at this
  effect size are dominated by between-domain variance.

### Knowledge Base Design

The synthetic KB MUST preserve these honesty invariants:

1. **One normative convention per doc.** The answer is an arbitrary unique token not derivable
   from the question.
2. **Topic/token split.** The topic phrase appears ONLY in title + Context. The answer token
   appears ONLY in Decision + Example. A search excerpt alone MUST NOT contain the answer.
3. **Realistic doc size** (~550 tokens, 6 sections). Preload cost MUST NOT be understated.
4. **Multi-domain prefix coverage.** Any prefix of size N spans all domains.
5. **Filler disjointness.** A topic search returns exactly one result regardless of N.
6. **Exact-match grading.** The token MUST appear verbatim in the final response.

**[v2] A KB copy used for the plugin arm MUST pass `archcore status` cleanly.** WHEN conformance
edits are needed (e.g. tag casing), the harness MUST verify afterwards that every answer token
survives, and the diff MUST be reported. Retrieval difficulty MUST NOT change.

### Cost Metric

Let `ctx_in = input_tokens + cache_creation + cache_read`.

**Cold** — `ctx_in x $3/M + output_tokens x $15/M`. No turn model, order-independent.

**Realistic** — `turns = max(1, num_turns); prefix = ctx_in / turns;
realistic = prefix x (1.25 + 0.10 x (turns - 1)) x $3/M + output_tokens x $15/M`

**Warm** — `total_cost_usd`. Order-dependent; diagnostic only.

**[v2] Cold is the primary metric; the v1 revision's "realistic MUST be primary" is withdrawn.**
The realistic metric penalises turn reduction: with `ctx_in` held constant, fewer turns scores as
more expensive. When `mode=full` cut arm C from 5 turns to 3 at identical token volume, realistic
cost "rose" $0.147 to $0.212 while cold stayed flat ($0.432 to $0.437). WHEN arms under comparison
differ materially in turn count, the analysis MUST lead with cold. Conclusions SHOULD be checked
against both metrics, and any disagreement between them MUST be stated.

### Aggregation Rules

- Group by `(phase, N, task_id, arm)` for CLI; by `(domain, arm, batch_size)` for Plugin.
- **[v2]** For cost, report **median AND mean AND max AND tail frequency** (share of runs above
  2x the arm's own median). Median alone is insufficient: on the v2 workload, B3's median was
  2.5x below arm C while its mean was 29% above, because 35% of its runs spiral.
- **[v2]** Suite totals MUST be computed from means, not medians. A median-based total assumes
  every task is the typical task, which is exactly what a bimodal arm violates.
- Report **mean** for `pass_rate`, `err_rate`.
- Usable rows: `ctx_in > 1000`. Turn-capped rows: keep (real cost), and count them.

### Isolation Requirements

- MUST pass `--strict-mcp-config --mcp-config <file>` to every `claude -p` invocation.
- Arms C and D MUST use an MCP config activating archcore at the arm's working directory.
- Arms A / B1 / B2 / B3 MUST use `{"mcpServers":{}}`.
- Each (N, arm) pair MUST have its own directory copy.
- **[v2]** The D-arm MUST allow both `mcp__archcore__*` and `mcp__plugin_archcore_archcore__*`
  tool names, since a loaded plugin may expose the same server under a prefixed name.
- The user's default config dir (OAuth credentials) MUST be retained for authentication.

## Constraints

- Arms MUST NOT differ on the source substrate.
- The crossover anchor task MUST be identical for every cell and trial.
- The answer token MUST NOT appear in the source tree, filenames, or any CLAUDE.md index.
- **[v2]** A prior run's raw outputs MUST be preserved when a new run is recorded. Comparisons
  across runs are the only way to separate host regressions from tool changes.

## Invariants

- For any N and arm: `cold >= realistic >= warm`.
- B1/B2/B3/C at the same N carry exactly the same set of doc files.
- Arm A cost is independent of N.
- D and C-batch carry the same `.archcore/` docs; only the plugin flag differs **[v2]**.

## Failure Behavior

- IF `ctx_in <= 1000`, THEN the row MUST be excluded.
- IF a response carries `api_error_status`, THEN the harness MUST retry with backoff and MUST
  NOT record it as a measurement.
- IF grading fails, THEN `pass=0`; the row MUST remain in cost aggregation.
- IF the plugin arm's hook probe fails, THEN the run MUST be discarded (see Plugin Benchmark).

## Conformance

A benchmark phase is **conforming** if it satisfies all MUST-level requirements above.
Non-conforming results MUST be labeled exploratory and MUST NOT be compared against baseline
numbers. **[v2]** Cross-run comparison additionally requires that both runs state their host
version; absolute costs across host versions are not comparable, only within-run rankings.

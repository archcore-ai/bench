# Archcore Token Benchmark — Summary

**English** · [Русский](SUMMARY.ru.md)

> Reproducible measurement of whether Archcore saves tokens for an AI coding agent, at a fixed
> quality bar, against realistic baselines. Full methodology and data: [`ANALYSIS.md`](ANALYSIS.md).

---

## What was measured

A public Go project (`go-chi/chi`) with a synthetic knowledge base of project conventions.
Each task asks for a rule whose answer is an **arbitrary token buried inside one document** —
it cannot be guessed, only retrieved. Five access strategies were compared by counting
**exact API tokens** at **equal quality** (all arms answer correctly):

| Arm | Knowledge access |
|-----|-----------------|
| **A — cold** | no docs; agent digs through source code |
| **B1 — preload** | all docs loaded into `CLAUDE.md` upfront |
| **B2 — index+grep** | docs as files + a curated `CLAUDE.md` index |
| **B3 — blind grep** | docs as files, no index; agent uses built-in Grep |
| **C — archcore** | docs as files; discovery+retrieval via Archcore MCP |
| **D — plugin** | Arm C + `--plugin-dir`; `/archcore:context` skill |

CLI benchmark: 305 measurements (125 crossover + 180 workload), 0 failures.
Plugin benchmark: 120 measurements (3 trials × 5 domains × 4 batch sizes × 2 arms).

---

## CLI: Archcore as MCP server

Archcore's per-task cost is **flat in KB size**. Preloading everything into `CLAUDE.md` grows
linearly. The gap widens without bound as the KB grows.

| KB size | CLAUDE.md preload | files + grep | **Archcore CLI** |
|---------|-------------------|--------------|------------------|
| 1 doc   | $0.102            | $0.103       | $0.127           |
| 20 docs | $0.134            | $0.121       | $0.127           |
| 80 docs | $0.238            | $0.123       | $0.127           |
| 320 docs| $0.681            | $0.112       | $0.127           |

- Crossover vs `CLAUDE.md` preload: **~27 documents**. Beyond that Archcore is cheaper.
- At 320 docs: Archcore is **4.6× cheaper** than preload ($0.127 vs $0.681).
- vs "files + grep": **at parity** — both are $0.11–0.13/task across the full range.
- 100% task success, all KB sizes.

The mechanism: preload carries the entire KB in context on every turn (grows linearly);
Archcore retrieves only the relevant slice (flat). Per-task cost = 3 turns × ~$0.04/turn.

---

## Plugin: Archcore + Claude Code integration

The Plugin adds `/archcore:context <area>` to Claude Code sessions. When multiple questions are
asked about the same area in one session, the fixed per-session overhead (MCP schemas, system
prompt, source context) is paid once and amortized across all questions.

**Per-question cost at different batch sizes** (median, 5 domains, 3 trials):

| Questions / session | Plugin (D-arm) | Raw MCP (C-arm) | vs. CLI separate calls |
|---------------------|---------------|-----------------|------------------------|
| 1                   | $0.163        | $0.150          | −29%*                  |
| 2                   | $0.075        | $0.067          | −41%                   |
| **4**               | **$0.032**    | **$0.033**      | **−74%**               |
| 8                   | $0.015        | $0.014          | −88%                   |

*vs. CLI separate calls baseline of $0.127/question.

**Full workload** — 20 tasks as 5 domain sessions of 4 questions each:

| Strategy | Total cost | Saving |
|----------|-----------|--------|
| 20 × CLI separate calls | $2.54 | — |
| Plugin batch (5 × 4q) | **$0.649** | **−74%** |
| Raw MCP batch (5 × 4q) | $0.722 | −72% |

The Plugin is **10% cheaper** than raw MCP batch on the full suite. For `errors` and `testing`
domains (ADR-type documents), the Plugin is 20% cheaper than raw MCP at batch size 4 — the
context skill helps the agent locate relevant documents more directly.

---

## CLI vs Plugin

|  | CLI (one call / question) | Plugin (batch session) |
|--|--------------------------|------------------------|
| Cost per question | $0.127 | $0.163 (N=1) → $0.032 (N=4) |
| Break-even vs CLI | — | N ≥ 2 questions per area |
| Full 20-task suite | $2.54 | $0.649 (−74%) |
| Cost consistency (IQR at N=4) | $0.008/q | $0.001/q |
| Best for | Scripts, single lookups | Interactive sessions |
| vs CLAUDE.md preload | 4.6× cheaper at 320 docs | — |

---

## Bottom line

**CLI** is the right choice when querying a knowledge base from scripts, single-shot pipelines,
or any workflow where sessions contain one question per run. Its cost is flat at $0.127/task
regardless of KB size, and on par with "markdown files + grep" — without any index to maintain.

**Plugin** is the right choice for interactive Claude Code sessions where a developer asks
multiple questions about the same area. At 4+ questions per session, cost drops to $0.032/q
(−74%) versus CLI per-question calls. The break-even is at ~2 questions.

**What cannot be claimed:** Archcore is not cheaper than every baseline. It does not beat
"files + grep" on a per-question basis. The honest token story is *scalability vs. preload*
and *parity with grep* — Archcore's structural value (relations, governance, zero index
maintenance, drift detection) is largely independent of token cost.

---

📄 Full methodology, all numbers, and what you cannot claim → [`ANALYSIS.md`](ANALYSIS.md)
📊 Raw scale tables → [`scale/FINDINGS_SCALE.md`](scale/FINDINGS_SCALE.md)

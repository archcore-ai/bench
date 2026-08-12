# Archcore token benchmark: summary

**English** · [Русский](SUMMARY.ru.md)

Five-minute version. Full detail: [`ANALYSIS.md`](ANALYSIS.md).

Run of 2026-08-12, on archcore CLI v0.7.0, plugin v0.7.1, Claude Code 2.1.228, model sonnet-5.
425 measurements. Every arm that carries the knowledge answered every task correctly.

---

## What was measured

Token cost to answer a question at equal quality. Each task asks for a normative convention
whose answer is an arbitrary token buried in one document. The token cannot be derived from the
source code, so an arm answers correctly only if it actually retrieved the fact. Grading is exact
token match.

| Arm | Knowledge access |
|-----|-----------------|
| A, cold | no docs; agent digs through source code |
| B1, preload | all docs loaded into `CLAUDE.md` upfront |
| B2, index+grep | docs as files plus a curated `CLAUDE.md` index |
| B3, blind grep | docs as files, no index; agent uses built-in Grep |
| C, archcore | docs as files; discovery and retrieval via Archcore MCP |
| D, plugin | arm C plus `--plugin-dir`; SessionStart context injection |

---

## CLI: Archcore as MCP server

Cost per task as the knowledge base grows (cold $, median):

| KB size | CLAUDE.md preload | files + grep | Archcore CLI |
|---------|-------------------|--------------|--------------|
| 1 doc   | 0.139             | 0.174        | 0.434        |
| 20 docs | 0.175             | 0.177        | 0.434        |
| 80 docs | 0.290             | 0.184        | 0.441        |
| 320 docs| 0.784             | 1.350        | 0.435        |

Archcore's cost is flat. It used 3 turns and 143k to 146k context tokens at every KB size, in all
25 runs, and it is the only arm that does not move. Preload grows linearly with the KB. The grep
baselines stay cheap up to about 80 documents and then climb steeply. Archcore overtakes preload
somewhere around 100 to 150 documents, and the grep baselines around 90 to 110.

On a 20-task suite at 80 documents (60 runs per arm), the median and the mean disagree, and the
gap between them is where the interesting behaviour sits:

| Arm | median | mean | max | runs above 2× median |
|-----|--------|------|-----|----------------------|
| files + grep | 0.178 | 0.608 | 2.400 | 22/60 |
| files + index | 0.597 | 0.607 | 1.224 | 1/60 |
| Archcore | 0.437 | 0.470 | 0.635 | 0/60 |

By median, grep costs 2.5× less than Archcore. By mean, Archcore costs 23% less than either
baseline. Both numbers describe the same 60 runs. Grep resolves in a single turn about 65% of the
time and spirals past 400k tokens the rest of the time. Archcore never spiraled once.

Suite total: Archcore $9.40, files+index $12.14, files+grep $12.17. Latency follows the same
shape: Archcore averages 8.8 s with a worst case of 16.5 s, while grep averages 16.3 s and peaked
at 93 s.

---

## Plugin: cost-neutral for retrieval

Plugin v0.7 removed `/archcore:context`. Context now arrives through a SessionStart hook that
injects a corpus header of roughly 150 tokens (document counts, tags, a pointer to the tools) and
no document bodies at all.

We measured plugin-on against plugin-off across 4 batch sizes, 120 runs. Turn counts came out
identical. Paired by domain and trial, the plugin won 8 of 15, 3 of 15, 7 of 15, and 8 of 15
comparisons, which is what a coin flip looks like. The context delta stayed inside the noise.
The plugin does not change retrieval cost.

What does save money is batching, and it works with or without the plugin:

| Questions per session | cost per question | vs 1 per session |
|-----------------------|-------------------|------------------|
| 1                     | 0.461             | baseline         |
| 2                     | 0.248             | 46% less         |
| 4                     | 0.132             | 71% less         |
| 8                     | 0.074             | 84% less         |

The v1 report credited this saving to the plugin. It belongs to session batching.

---

## Bottom line

Three things drive the bill, and they are very different in size:

| What you change | Cost multiple |
|---|---|
| Ask 8 questions in one session instead of 8 separate ones | 6.2× |
| Stop keeping all documentation in `CLAUDE.md` (1 doc vs 320) | 5.6× |
| Switch to the cheapest search method (at 80 documents) | 1.3× |

The search method matters least. Start with the top row. Batching was measured on Archcore only;
the other methods were not run that way.

**Choose by knowledge base size.** Under 50 documents, `CLAUDE.md` or plain grep costs less. Over
100 to 150, Archcore costs less than anything else. In between, the difference is inside the
margin of error.

**Choose Archcore anyway if the worst case hurts more than the typical one.** It never blew up
once in 60 runs; grep blew up 22 times, up to $2.40 for a single task. It is also the fastest on
average, 8.8 s against 16.3 s, with a worst case of 16.5 s against 93 s.

**The plugin does not make search cheaper.** Install it for `document`, `plan`, and `review`.

## What this does not measure

Answer quality. Every method that has the documents answers correctly, by design, so that cost can
be compared at equal results. Nothing here shows whether Archcore makes answers better.

Also out of scope: reasoning across several documents, document relations, drift, and governance.
Those are the features most teams adopt Archcore for, and this benchmark does not touch them.

## One caveat on the numbers

In May, on an earlier Claude Code, Archcore was the most expensive method on this suite. It is now
the cheapest, and its own cost barely moved, from 142k to 144k tokens. What changed is that Claude
Code 2.1.228 made `Grep` and `Read` 2.4× to 3.5× more expensive on large knowledge bases. These
comparisons hold for the host version they were measured on.

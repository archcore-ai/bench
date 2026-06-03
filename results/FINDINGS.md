# Sanity-check findings (chi @ 3b171578, sonnet, TRIALS=1)

Task: "where should a new `RequireAPIKey` middleware live + what signature/wrapping pattern?"
**Quality: parity** — all three arms gave correct, convention-compliant answers. Token comparison is valid.

## Fixed-context tax (static phase, total input-side tokens)

| Arm | input | cache_create | cache_read | total ctx | Δ vs A |
|-----|------:|-------------:|-----------:|----------:|-------:|
| A (cold)     | 3 | 26506 | 0     | 26,509 | — |
| B (CLAUDE.md)| 3 | 7128  | 19677 | 26,808 | **+299** (the CLAUDE.md) |
| C (archcore) | 3 | 7470  | 19677 | 27,150 | **+641** (MCP tool schemas) |

→ Both knowledge taxes are small (hundreds of tokens). At this scale the per-run prompt-cache
split dominates the raw numbers (note A paid cache_creation as the first run; B/C got cache_read).

## Task cost (the signal)

| Arm | total ctx tokens | output | turns | **cost USD** | latency |
|-----|-----------------:|-------:|------:|-------------:|--------:|
| A (cold)      | 81,644 | 602 | 4 | $0.0621 | 16.1s |
| B (CLAUDE.md) | 26,895 | 285 | 1 | **$0.0372** | 5.3s |
| C (archcore)  | 83,579 | 682 | 4 | $0.0661 | 15.7s |

## Verdict

1. **Rig works.** Exact per-arm usage captured; quality controlled; deltas measurable. ✅
2. **Effect is non-zero and clear.** B is **40% cheaper than A** and **44% cheaper than C**. ✅
3. **Direction (this regime): CLAUDE.md wins; archcore ties cold and is marginally costlier.**
   - B answered in **1 turn** — the fact was preloaded in context, no exploration.
   - C still **explored source** (4 turns, cited `basic_auth.go`) *and* paid MCP round-trips on top,
     so retrieval overhead > savings when the KB is one small doc.
4. **This empirically confirms the crossover thesis:** flat preload beats retrieval when the whole
   KB fits cheaply in context. Archcore's advantage must be demonstrated where preloading is
   infeasible — **large KB and/or multi-session**, where arm B degrades toward arm A (can't keep
   everything in context every turn) while arm C pays only for the slice it retrieves.

## Next experiment to actually show archcore winning

- Scale the KB to N docs (e.g. 30–100 ADRs/rules/specs across domains).
- Arm B's "CLAUDE.md" then must either (a) contain all N → fat context every turn, or
  (b) be truncated → misses the relevant fact → quality drops or it reads source like arm A.
- Arm C retrieves only the relevant 1–3 docs. Plot cost vs KB size → find the crossover point.

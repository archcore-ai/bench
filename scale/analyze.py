#!/usr/bin/env python3
"""Aggregate the scale-benchmark CSV into a crossover table + workload totals.

Two cost views (the prompt-cache confounder, bracketed rather than fought):
  * cold-session cost  = (input+cache_creation+cache_read) * INPUT_RATE + output * OUTPUT_RATE
       order-independent; models a fresh context per task (multi-session regime).
  * warm billed cost   = the actually-billed total_cost_usd (cache-discounted; one long session).
The truth for a given team lives between these two; we report both.

Usage: analyze.py [results.csv]
"""
import csv
import statistics as st
import sys
from collections import defaultdict

# Claude Sonnet 4.x list price (USD per token)
INPUT_RATE = 3.0 / 1e6
OUTPUT_RATE = 15.0 / 1e6
CACHE_WRITE = 1.25   # cache_creation billed at 1.25x input
CACHE_READ = 0.10    # cache_read billed at 0.10x input

CSVPATH = sys.argv[1] if len(sys.argv) > 1 else "results/results.csv"
ARM_LABEL = {"A": "A cold", "B1": "B1 preload", "B2": "B2 index+grep",
             "B3": "B3 blind grep", "C": "C archcore"}
ARM_SEQ = ["A", "B1", "B2", "B3", "C"]


def med(xs):
    return st.median(xs) if xs else 0.0


def load(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            ctx_in = int(r["input_tokens"]) + int(r["cache_creation"]) + int(r["cache_read"])
            out = int(r["output_tokens"])
            r["_ctx_in"] = ctx_in
            r["_out"] = out
            r["_cold"] = ctx_in * INPUT_RATE + out * OUTPUT_RATE
            r["_warm"] = float(r["total_cost_usd"])
            # Realistic per-task cold-start cost (order-independent): a fresh session per task,
            # but intra-task agent turns are cache-hit (they're consecutive in one CLI call).
            # prefix ~= ctx_in/turns (avg per-turn context); first turn creates the cache,
            # the other (turns-1) re-read it cheaply. This is the fair metric — pure _cold
            # over-charges multi-turn arms; _warm is polluted by cross-run cache bleed.
            turns = max(1, int(r["num_turns"]))
            prefix = ctx_in / turns
            r["_real"] = (prefix * (CACHE_WRITE + CACHE_READ * (turns - 1))) * INPUT_RATE \
                + out * OUTPUT_RATE
            r["_err"] = int(r.get("is_error") or 0)
            r["_pass"] = int(r["pass"])
            r["_turns"] = int(r["num_turns"])
            r["N"] = int(r["N"])
            rows.append(r)
    return rows


def agg(rows):
    """group -> dict of medians/means over trials"""
    g = defaultdict(list)
    for r in rows:
        g[(r["phase"], r["N"], r["task_id"], r["arm"])].append(r)
    out = {}
    for k, rs in g.items():
        # A run counts for cost if it produced real usage. max_turns runs DO (they flail and
        # bill tokens — that IS the floor's cost). Only true no-usage errors (API/overflow) are
        # dropped and flagged separately.
        ok = [x for x in rs if x["_ctx_in"] > 1000]
        out[k] = {
            "pass_rate": sum(x["_pass"] for x in rs) / len(rs),
            "err_rate": sum(x["_err"] for x in rs) / len(rs),
            "usable": len(ok),
            "real": med([x["_real"] for x in ok]),
            "cold": med([x["_cold"] for x in ok]),
            "warm": med([x["_warm"] for x in ok]),
            "ctx": med([x["_ctx_in"] for x in ok]),
            "turns": med([x["_turns"] for x in ok]),
            "n": len(rs),
        }
    return out


def crossover_table(rows):
    a = agg([r for r in rows if r["phase"] == "crossover"])
    Ns = sorted({k[1] for k in a})
    arms = [x for x in ARM_SEQ if any(k[3] == x for k in a)]
    task_id = next((k[2] for k in a), "000")
    print("## Crossover — fixed task, KB size N sweep\n")
    print("Cost = **realistic per-task** USD (fresh session, intra-task turns cached; "
          "order-independent). pass = fraction correct over trials.\n")
    # header
    h = "| N | " + " | ".join("{} $".format(ARM_LABEL[x]) for x in arms) + " | " + \
        " | ".join("{} pass".format(x) for x in arms) + " |"
    sep = "|" + "---|" * (1 + 2 * len(arms))
    print(h); print(sep)
    for N in Ns:
        cells = []
        for x in arms:
            v = a.get(("crossover", N, task_id, x))
            if not v:
                cells.append("—")
            elif v["usable"] == 0:
                cells.append("✗err")  # no usable usage (API error / context overflow)
            else:
                cells.append("{:.4f}".format(v["real"]))
        for x in arms:
            v = a.get(("crossover", N, task_id, x))
            cells.append("{:.0%}".format(v["pass_rate"]) if v else "—")
        print("| {} | {} |".format(N, " | ".join(cells)))
    print()
    # context-token volume (the cache-independent mechanism)
    print("### Context tokens processed (input+cache_create+cache_read+output), median\n")
    print("| N | " + " | ".join(ARM_LABEL[x] for x in arms) + " |")
    print("|" + "---|" * (1 + len(arms)))
    for N in Ns:
        cells = []
        for x in arms:
            v = a.get(("crossover", N, task_id, x))
            cells.append("{:,}".format(int(v["ctx"] + v["turns"] * 0)) if v else "—")
        # ctx already includes output via _ctx_in? no -> add output median sep; keep ctx input-side
        print("| {} | {} |".format(N, " | ".join(cells)))
    print()
    print("### Turns (median)\n")
    print("| N | " + " | ".join(ARM_LABEL[x] for x in arms) + " |")
    print("|" + "---|" * (1 + len(arms)))
    for N in Ns:
        cells = [("{:.0f}".format(a[("crossover", N, task_id, x)]["turns"])
                  if ("crossover", N, task_id, x) in a else "—") for x in arms]
        print("| {} | {} |".format(N, " | ".join(cells)))
    print()


def workload_table(rows):
    wl = [r for r in rows if r["phase"] == "workload"]
    if not wl:
        return
    a = agg(wl)
    arms = [x for x in ARM_SEQ if any(k[3] == x for k in a)]
    tasks = sorted({k[2] for k in a})
    N = next(iter({k[1] for k in a}))
    print("## Workload — fixed KB (N={}), {}-task suite\n".format(N, len(tasks)))
    print("Per-arm **suite total** = sum over tasks of the median per-task cost "
          "(cost to run the whole suite once).\n")
    print("| Arm | suite realistic $ | (cold) | (warm) | pass | med turns/task | med ctx/task |")
    print("|---|---|---|---|---|---|---|")
    for x in arms:
        cells = [a[("workload", N, t, x)] for t in tasks if ("workload", N, t, x) in a]
        real = sum(c["real"] for c in cells)
        cold = sum(c["cold"] for c in cells)
        warm = sum(c["warm"] for c in cells)
        pr = sum(c["pass_rate"] for c in cells) / len(cells)
        turns = med([c["turns"] for c in cells])
        ctx = med([c["ctx"] for c in cells])
        print("| {} | {:.4f} | {:.4f} | {:.4f} | {:.0%} | {:.0f} | {:,} |".format(
            ARM_LABEL[x], real, cold, warm, pr, turns, int(ctx)))
    print()


def _series(a, task_id, arm, metric):
    """sorted [(N, value)] for a passing arm on a metric ('cold'|'warm'), skipping errored cells."""
    pts = []
    for (ph, N, t, x), v in a.items():
        if ph == "crossover" and t == task_id and x == arm and v["usable"] > 0:
            pts.append((N, v[metric]))
    return sorted(pts)


def _crossover_N(challenger, baseline):
    """First N where challenger becomes <= baseline, linearly interpolated. None if never."""
    bd = dict(baseline)
    common = [N for N, _ in challenger if N in bd]
    prev = None
    for N in sorted(common):
        cv = dict(challenger)[N]
        diff = cv - bd[N]  # <=0 means challenger now cheaper
        if prev is not None:
            pN, pdiff = prev
            if pdiff > 0 and diff <= 0:  # sign change -> interpolate
                frac = pdiff / (pdiff - diff)
                return pN + frac * (N - pN)
        if diff <= 0 and prev is None:
            return float(N)  # already cheaper at the smallest N
        prev = (N, diff)
    return None


def summary(rows):
    a = agg([r for r in rows if r["phase"] == "crossover"])
    if not a:
        return
    task_id = next((k[2] for k in a), "000")
    Ns = sorted({k[1] for k in a})
    arms = [x for x in ARM_SEQ if any(k[3] == x for k in a)]
    print("## Verdict — cheapest arm at each N (realistic per-task cost, passing only)\n")
    print("| N | ranking (cheapest → priciest) |")
    print("|---|---|")
    for N in Ns:
        ranked = sorted(
            [(a[("crossover", N, task_id, x)]["real"], x) for x in arms
             if ("crossover", N, task_id, x) in a
             and a[("crossover", N, task_id, x)]["usable"] > 0
             and a[("crossover", N, task_id, x)]["pass_rate"] > 0.5],
            key=lambda z: z[0])
        s = "  <  ".join("{} (${:.3f})".format(ARM_LABEL[x], c) for c, x in ranked)
        # arms that answered correctly but cost more, and arms that failed (incl. cold floor)
        failed = [ARM_LABEL[x] for x in arms
                  if ("crossover", N, task_id, x) in a
                  and a[("crossover", N, task_id, x)]["pass_rate"] <= 0.5]
        if failed:
            s += "  |  ✗fail: " + ", ".join(failed)
        print("| {} | {} |".format(N, s))
    print()
    print("### Crossover points — N where **C (archcore)** overtakes a baseline\n")
    rC = _series(a, task_id, "C", "real")
    print("| vs baseline | realistic N* | (no-cache N*) |")
    print("|---|---|---|")
    for base in ["B1", "B2", "B3"]:
        rN = _crossover_N(rC, _series(a, task_id, base, "real"))
        cN = _crossover_N(_series(a, task_id, "C", "cold"), _series(a, task_id, base, "cold"))
        f = lambda x: "never (in range)" if x is None else "≈ {:.0f} docs".format(x)
        print("| C vs {} | {} | {} |".format(ARM_LABEL[base], f(rN), f(cN)))
    print("\n_N* = KB size where archcore's cost drops to/below the baseline. "
          "\"never\" = baseline stays cheaper across the whole tested range._\n")


def ascii_chart(rows):
    a = agg([r for r in rows if r["phase"] == "crossover"])
    if not a:
        return
    task_id = next((k[2] for k in a), "000")
    Ns = sorted({k[1] for k in a})
    arms = [x for x in ARM_SEQ if any(k[3] == x for k in a)]
    vals = [a[("crossover", N, task_id, x)]["real"] for N in Ns for x in arms
            if ("crossover", N, task_id, x) in a and a[("crossover", N, task_id, x)]["usable"] > 0]
    if not vals:
        return
    hi = max(vals)
    print("## Realistic per-task cost vs N (each █ ≈ ${:.3f})\n".format(hi / 40))
    print("```")
    for x in arms:
        print("{:<16}".format(ARM_LABEL[x]))
        for N in Ns:
            v = a.get(("crossover", N, task_id, x))
            if not v:
                continue
            if v["usable"] == 0:
                bar, tag = "", "✗ no usable usage (API error / overflow)"
            else:
                bar = "█" * max(1, int(round(v["real"] / hi * 40)))
                tag = "${:.3f}".format(v["real"])
            print("  N={:<4} {:<41} {}".format(N, bar, tag))
    print("```\n")
    # show the cache-regime spread for the two extremes (real is the middle, honest case)
    print("### Cost-model spread (per task) — real is the headline; cold/warm bound it\n")
    print("| arm @ N=max | realistic | no-cache (cold) | measured warm |")
    print("|---|---|---|---|")
    Nmax = Ns[-1]
    for x in arms:
        v = a.get(("crossover", Nmax, task_id, x))
        if v and v["usable"]:
            print("| {} @ N={} | ${:.3f} | ${:.3f} | ${:.3f} |".format(
                ARM_LABEL[x], Nmax, v["real"], v["cold"], v["warm"]))
    print()


def main():
    rows = load(CSVPATH)
    print("# Scale benchmark results\n")
    print("_source: `{}` ; cold-session priced at Sonnet list ${}/M in, ${}/M out_\n".format(
        CSVPATH, int(INPUT_RATE * 1e6), int(OUTPUT_RATE * 1e6)))
    summary(rows)
    crossover_table(rows)
    ascii_chart(rows)
    workload_table(rows)


if __name__ == "__main__":
    main()

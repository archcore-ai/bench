#!/usr/bin/env python3
"""Compare a v2 benchmark run against the v1 baseline, with distribution-aware statistics.

Why this exists alongside analyze.py: analyze.py reports medians. Under Claude Code 2.1.228
the grep arms became bimodal — a run either resolves in one turn or spirals for 9-17 turns —
and a median hides exactly the behaviour that decides the cost of running a suite. This script
reports median AND mean AND tail frequency, because for a team paying per task over many
tasks the mean is the number that lands on the invoice.

Usage: python3 analyze_v2.py [v2.csv] [v1.csv]
"""
import csv
import statistics
import sys

IN_RATE, OUT_RATE = 3.0 / 1e6, 15.0 / 1e6
ARMS = ["A", "B1", "B2", "B3", "C"]
LABEL = {"A": "A cold", "B1": "B1 preload", "B2": "B2 index+grep",
         "B3": "B3 blind grep", "C": "C archcore"}


def ctx(r):
    return int(r["input_tokens"]) + int(r["cache_creation"]) + int(r["cache_read"])


def cold(r):
    """Order-independent: every turn re-sends context as fresh input. No turn model."""
    return ctx(r) * IN_RATE + int(r["output_tokens"]) * OUT_RATE


def realistic(r):
    """Fresh session per task, cached within the task. Assumes a ~constant per-turn prefix."""
    t = max(1, int(r["num_turns"]))
    return (ctx(r) / t) * (1.25 + 0.10 * (t - 1)) * IN_RATE + int(r["output_tokens"]) * OUT_RATE


def load(path, phase):
    with open(path) as fh:
        return [r for r in csv.DictReader(fh)
                if r["phase"] == phase and int(r["is_error"]) == 0]


def med(xs):
    return statistics.median(xs) if xs else float("nan")


def mean(xs):
    return statistics.fmean(xs) if xs else float("nan")


def fmt(x, w=7, p=3):
    return f"{x:>{w}.{p}f}" if x == x else f"{'—':>{w}}"


def crossover(v2, v1):
    print("## Crossover — anchor task, KB size sweep\n")
    for name, fn in (("realistic", realistic), ("cold", cold)):
        print(f"### {name} $/task — median (v1 → v2)\n")
        print(f"| N | " + " | ".join(LABEL[a] for a in ARMS) + " |")
        print("|" + "---|" * (len(ARMS) + 1))
        for N in (1, 20, 80, 160, 320):
            cells = []
            for a in ARMS:
                s1 = [fn(r) for r in v1 if int(r["N"]) == N and r["arm"] == a]
                s2 = [fn(r) for r in v2 if int(r["N"]) == N and r["arm"] == a]
                cells.append(f"{med(s1):.3f} → {med(s2):.3f}" if s2 else "—")
            print(f"| {N} | " + " | ".join(cells) + " |")
        print()

    print("### Spread per cell (v2): context tokens, k — every trial\n")
    for a in ARMS:
        row = []
        for N in (1, 20, 80, 160, 320):
            s = sorted(round(ctx(r) / 1000) for r in v2 if int(r["N"]) == N and r["arm"] == a)
            row.append(f"N={N}: {s}")
        print(f"- **{LABEL[a]}** — " + "; ".join(row))
    print()

    print("### Turns, median (v1 → v2)\n")
    print("| N | " + " | ".join(LABEL[a] for a in ARMS) + " |")
    print("|" + "---|" * (len(ARMS) + 1))
    for N in (1, 20, 80, 160, 320):
        cells = []
        for a in ARMS:
            t1 = [int(r["num_turns"]) for r in v1 if int(r["N"]) == N and r["arm"] == a]
            t2 = [int(r["num_turns"]) for r in v2 if int(r["N"]) == N and r["arm"] == a]
            cells.append(f"{med(t1):.0f} → {med(t2):.0f}" if t2 else "—")
        print(f"| {N} | " + " | ".join(cells) + " |")
    print()


def workload(v2, v1, arms=("B2", "B3", "C")):
    print("## Workload — N=80, 20-task suite\n")
    print("### Distribution per task (v2)\n")
    print("| Arm | n | median $ | **mean $** | min | max | max/med | runs >2× med | turns med | pass |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for a in arms:
        rs = [r for r in v2 if r["arm"] == a]
        if not rs:
            continue
        c = [cold(r) for r in rs]
        m = med(c)
        tail = sum(1 for x in c if x > 2 * m)
        p = sum(int(r["pass"]) for r in rs)
        print(f"| {LABEL[a]} | {len(rs)} | {m:.3f} | **{mean(c):.3f}** | {min(c):.3f} | "
              f"{max(c):.3f} | {max(c)/m:.1f}× | {tail}/{len(rs)} | "
              f"{med([int(r['num_turns']) for r in rs]):.0f} | {p}/{len(rs)} |")
    print()

    print("### Suite total — cost to answer all 20 tasks once\n")
    print("| Arm | v1 median-based | v2 median-based | **v2 mean-based** | v2/v1 (mean) |")
    print("|---|---|---|---|---|")
    for a in arms:
        r1 = [cold(r) for r in v1 if r["arm"] == a]
        r2 = [cold(r) for r in v2 if r["arm"] == a]
        if not r2:
            continue
        s1, s2, s2m = med(r1) * 20, med(r2) * 20, mean(r2) * 20
        base = mean(r1) * 20
        print(f"| {LABEL[a]} | {s1:.2f} | {s2:.2f} | **{s2m:.2f}** | {s2m/base:.2f}× |")
    print()
    print("Median-based totals assume every task is the typical task — which is exactly the "
          "assumption a bimodal arm violates. The mean-based column is what a suite actually costs.\n")


def main():
    v2p = sys.argv[1] if len(sys.argv) > 1 else "results/results_v2.csv"
    v1p = sys.argv[2] if len(sys.argv) > 2 else "results/results_v1.csv"
    print(f"# Benchmark v2 vs v1\n\nv2: `{v2p}` · v1: `{v1p}`\n")
    crossover(load(v2p, "crossover"), load(v1p, "crossover"))
    print("---\n")
    workload(load(v2p, "workload"), load(v1p, "workload"))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Materialize one arm's working directory for a given KB size N.

Usage: build_arm.py <arm: A|B1|B2|C> <N> <out_repo_dir>

All arms get the same chi source substrate (read-only context). Knowledge differs:
  A  -> nothing (cold; models a repo with no agent docs)
  B1 -> CLAUDE.md = full bodies of the first N docs concatenated (preload-everything)
  B2 -> .archcore/ with first N docs as files + CLAUDE.md index (paths+topics, NO tokens) ; no MCP
  B3 -> .archcore/ with first N docs as files, NO index/CLAUDE.md ; agent discovers via Grep/Glob
  C  -> .archcore/ with first N docs as files ; archcore MCP supplies discovery+retrieval

B1, B2, B3, C carry IDENTICAL facts (same N docs); only the rendering/access differs.
B3 vs C isolates "built-in Grep over markdown" vs "archcore MCP retrieval" (same files, same
zero index maintenance). A is the floor.
"""
import csv
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KB = os.path.join(HERE, "kb")
FACTS = os.path.join(HERE, "facts.csv")
CHI = os.environ.get("CHI_REPO") or os.path.join(HERE, "..", "repos", "chi")


def load_facts():
    with open(FACTS) as f:
        return list(csv.DictReader(f))


def strip_frontmatter(md):
    # remove leading YAML --- ... --- block
    return re.sub(r"^---\n.*?\n---\n", "", md, count=1, flags=re.DOTALL)


def copy_chi(dst):
    os.makedirs(dst, exist_ok=True)
    # copy chi source as read-only substrate, excluding .git to save space/time
    subprocess.run(
        ["rsync", "-a", "--exclude", ".git", CHI + "/", dst + "/"],
        check=True,
    )


def main():
    arm, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    facts = load_facts()[:n]
    if os.path.isdir(out):
        shutil.rmtree(out)
    copy_chi(out)

    if arm == "A":
        pass  # cold: no knowledge

    elif arm == "B1":
        parts = ["# Project conventions\n",
                 "Authoritative team conventions for this service. Follow them exactly.\n"]
        for r in facts:
            body = strip_frontmatter(open(os.path.join(KB, r["path"])).read()).strip()
            parts.append("\n---\n\n" + body + "\n")
        with open(os.path.join(out, "CLAUDE.md"), "w") as f:
            f.write("\n".join(parts))

    elif arm in ("B2", "B3", "C"):
        adir = os.path.join(out, ".archcore")
        for r in facts:
            src = os.path.join(KB, r["path"])
            dst = os.path.join(adir, r["path"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)
        # B3: files only, no index, no MCP -> agent must discover via Grep/Glob
        if arm == "B2":
            # index/map so the agent knows which docs exist and where (strong grep baseline).
            lines = ["# Project conventions index\n",
                     "Team conventions live as Markdown files under `.archcore/`. "
                     "Open the relevant file to get the exact rule.\n"]
            for r in facts:
                lines.append("- `.archcore/{}` — {}".format(r["path"], r["topic"]))
            with open(os.path.join(out, "CLAUDE.md"), "w") as f:
                f.write("\n".join(lines) + "\n")
        # C: no CLAUDE.md — discovery+retrieval via archcore MCP (server instructions guide it)

    else:
        sys.exit("unknown arm: " + arm)

    print("built {} N={} -> {}".format(arm, n, out))


if __name__ == "__main__":
    main()

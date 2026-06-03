#!/usr/bin/env python3
"""Grade one run: did the model's final answer contain the expected token?

Usage: grade.py <raw_run.json> <answer_token>  ->  prints "1" (pass) or "0" (fail)

Pass = the exact answer token appears as a substring of the run's `.result`
(case-insensitive). The token is arbitrary/non-guessable, so a pass means the
model actually had the fact (from preload or retrieval), not a lucky guess.
"""
import json
import sys


def main():
    path, token = sys.argv[1], sys.argv[2]
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        print("0")
        return
    result = data.get("result")
    if not isinstance(result, str):
        print("0")
        return
    print("1" if token.lower() in result.lower() else "0")


if __name__ == "__main__":
    main()

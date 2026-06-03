---
title: "Project stack"
status: accepted
tags:
  - "conventions"
  - "stack"
---

Code in Python (benchmark scripts) and shell (harness runner).
Evaluate benchmark arms via the Claude CLI (`claude -p --output-format json`); do not introduce alternative evaluation runners without an ADR.
Test fixtures use Go (the chi router); do not modify files under `repos/`, `runs/`, or `scale/arms/` directly — regenerate them via `build_arm.py`.
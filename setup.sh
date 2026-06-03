#!/usr/bin/env bash
# One-time setup: fetch the chi reference repo and build sanity-harness arm dirs.
# Run this once after cloning. Safe to re-run (skips steps already done).
#
# After this script completes you can run:
#   bash harness/bench.sh           -- sanity check (2 min)
#   cd scale && python3 gen_kb.py && bash run.sh all   -- full CLI benchmark
#   PLUGIN=/path/to/archcore-plugin bash scale/run_plugin.sh  -- plugin benchmark
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── 1. Clone chi source (used by both harness and scale benchmark) ────────────
if [ -d "$ROOT/repos/chi/.git" ] || [ -f "$ROOT/repos/chi/go.mod" ]; then
  echo "repos/chi already present, skipping clone"
else
  echo "Cloning go-chi/chi..."
  git clone --depth=1 https://github.com/go-chi/chi.git "$ROOT/repos/chi"
fi

# ── 2. Build sanity harness arm directories (runs/) ───────────────────────────
for arm in A B C; do
  if [ -f "$ROOT/runs/$arm/repo/go.mod" ]; then
    echo "runs/$arm already present, skipping"
    continue
  fi
  echo "Building runs/$arm..."
  mkdir -p "$ROOT/runs/$arm/repo"
  rsync -a --exclude .git "$ROOT/repos/chi/" "$ROOT/runs/$arm/repo/"
done

# B arm: inject the single-doc CLAUDE.md fixture (1-doc preload knowledge base)
cp "$ROOT/fixtures/chi/CLAUDE.md" "$ROOT/runs/B/repo/CLAUDE.md"

# C arm: inject archcore docs as .archcore/ (1-doc archcore knowledge base)
mkdir -p "$ROOT/runs/C/repo/.archcore"
rsync -a "$ROOT/fixtures/chi/archcore/" "$ROOT/runs/C/repo/.archcore/"

echo ""
echo "Setup complete."
echo ""
echo "Next steps:"
echo "  bash harness/bench.sh                              # sanity check (2 min)"
echo "  cd scale && python3 gen_kb.py && bash run.sh all   # full CLI benchmark (~90 min)"
echo "  PLUGIN=/path/to/archcore-plugin bash scale/run_plugin.sh  # plugin benchmark"

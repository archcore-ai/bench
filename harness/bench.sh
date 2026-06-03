#!/usr/bin/env bash
# Archcore token-savings sanity harness.
# Runs each arm (A=cold, B=CLAUDE.md, C=archcore) through two phases:
#   static = trivial prompt -> isolates fixed per-arm context tax
#   task   = knowledge question -> exercises discovery/retrieval cost
# Emits exact API usage (from claude -p --output-format json) to a CSV.
#
# NOT a benchmark result by itself: trials=1, single task, sonnet. Sanity only.
set -euo pipefail

BENCH="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${MODEL:-sonnet}"
TRIALS="${TRIALS:-1}"
MAXTURNS=12
RAW="$BENCH/results/raw"
CSV="$BENCH/results/results.csv"
mkdir -p "$RAW"

# Generate MCP config for arm C pointing at this machine's runs/C/repo
MCP_C="$RAW/mcp-archcore.json"
cat > "$MCP_C" <<EOF
{"mcpServers":{"archcore":{"command":"archcore","args":["mcp","--project","$BENCH/runs/C/repo"]}}}
EOF
echo "arm,phase,trial,input_tokens,cache_creation,cache_read,output_tokens,total_cost_usd,num_turns,duration_ms" > "$CSV"

STATIC_PROMPT='Reply with exactly the single word: ready'
TASK_PROMPT='A teammate wants to add a new chi middleware called RequireAPIKey that rejects any request missing an X-Api-Key header with HTTP 401. Following THIS repository'"'"'s conventions, answer concisely: (1) the exact file path the middleware should live in and its package, (2) the exact Go function signature(s) it should use, (3) the handler-wrapping pattern. Do NOT create or modify any files - just answer.'

run_one () {
  local arm="$1" phase="$2" trial="$3" workdir="$4" mcp="$5" prompt="$6"; shift 6
  local allowed=("$@")
  local out="$RAW/${arm}_${phase}_${trial}.json"
  ( cd "$workdir" && claude -p "$prompt" \
      --model "$MODEL" --output-format json \
      --strict-mcp-config --mcp-config "$mcp" \
      --dangerously-skip-permissions \
      --disallowedTools Write Edit MultiEdit NotebookEdit \
      --allowedTools "${allowed[@]}" \
      --max-turns "$MAXTURNS" ) > "$out" 2>/dev/null || true
  jq -r --arg arm "$arm" --arg phase "$phase" --arg trial "$trial" '
    [$arm,$phase,$trial,
     (.usage.input_tokens//0),(.usage.cache_creation_input_tokens//0),
     (.usage.cache_read_input_tokens//0),(.usage.output_tokens//0),
     (.total_cost_usd//0),(.num_turns//0),(.duration_ms//0)] | @csv' "$out" >> "$CSV"
  echo "  done: $arm/$phase/$trial"
}

READ_TOOLS=(Read Grep Glob)
ARCHCORE_TOOLS=(Read Grep Glob mcp__archcore__search_documents mcp__archcore__get_document mcp__archcore__list_documents)

for t in $(seq 1 "$TRIALS"); do
  echo "trial $t"
  run_one A static "$t" "$BENCH/runs/A/repo" "$BENCH/harness/mcp-empty.json"    "$STATIC_PROMPT" "${READ_TOOLS[@]}"
  run_one B static "$t" "$BENCH/runs/B/repo" "$BENCH/harness/mcp-empty.json"    "$STATIC_PROMPT" "${READ_TOOLS[@]}"
  run_one C static "$t" "$BENCH/runs/C/repo" "$MCP_C" "$STATIC_PROMPT" "${ARCHCORE_TOOLS[@]}"
  run_one A task   "$t" "$BENCH/runs/A/repo" "$BENCH/harness/mcp-empty.json"    "$TASK_PROMPT"   "${READ_TOOLS[@]}"
  run_one B task   "$t" "$BENCH/runs/B/repo" "$BENCH/harness/mcp-empty.json"    "$TASK_PROMPT"   "${READ_TOOLS[@]}"
  run_one C task   "$t" "$BENCH/runs/C/repo" "$MCP_C" "$TASK_PROMPT"   "${ARCHCORE_TOOLS[@]}"
done

echo "=== results.csv ==="
column -t -s, "$CSV"

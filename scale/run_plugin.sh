#!/usr/bin/env bash
# Plugin benchmark driver: measures D-arm (plugin + batch) vs C-arm (batch) economics.
#
# Design:
#   D-batch(N): /archcore:context <domain> + N questions in one claude -p call, --plugin-dir
#   C-batch(N): N questions in one claude -p call, no plugin (control)
#   C-sep:      1 question per call, no plugin (v1 baseline — taken from results.csv, not re-run)
#
# Output: bench/scale/results/plugin_results.csv
#
# Usage: run_plugin.sh [--batch-sizes "1 2 4 8"] [--trials 3] [--domains "middleware routing ..."]
#
# Requires: plugin_tasks.json at bench root; N=80 arm dirs already built (run.sh first).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH="$ROOT/scale"
MODEL="${MODEL:-sonnet}"
MAXTURNS="${MAXTURNS:-30}"
TIMEOUT="${TIMEOUT:-300}"
RETRIES="${RETRIES:-1}"
TRIALS="${TRIALS:-3}"
BATCH_SIZES="${BATCH_SIZES:-1 2 4 8}"
DOMAINS="${DOMAINS:-middleware routing errors logging testing}"
RESULTS="$BENCH/results"
RAW="$RESULTS/raw_plugin"
CSV="${CSV:-$RESULTS/plugin_results.csv}"

# PLUGIN: path to the archcore plugin directory (must contain .claude-plugin/plugin.json).
# Clone https://github.com/archcore-ai/plugin and point this at it.
# Defaults to a sibling directory named "plugin" next to the bench repo.
if [ -z "${PLUGIN:-}" ]; then
  CANDIDATE="$(cd "$ROOT/.." && pwd)/plugin"
  if [ -f "$CANDIDATE/.claude-plugin/plugin.json" ]; then
    PLUGIN="$CANDIDATE"
  else
    echo "ERROR: PLUGIN env var not set and no plugin found at $CANDIDATE"
    echo "  Clone the plugin: git clone https://github.com/archcore-ai/plugin /path/to/plugin"
    echo "  Then run:         PLUGIN=/path/to/plugin bash scale/run_plugin.sh"
    exit 1
  fi
fi

WSIZE=80
WORKDIR="$BENCH/arms/N${WSIZE}/C/repo"
MCP="$BENCH/arms/N${WSIZE}/mcp-C.json"
TOOLS="Read Grep Glob mcp__archcore__search_documents mcp__archcore__get_document mcp__archcore__list_documents"

mkdir -p "$RAW"

HDR="batch_size,domain,arm,trial,n_correct,n_total,pass_rate,input_tokens,cache_creation,cache_read,output_tokens,total_cost_usd,num_turns,duration_ms,is_error"
echo "$HDR" > "$CSV"

# Build batch prompt for D-arm: context load + N questions
build_d_prompt () {
  local domain="$1" n="$2"
  local questions
  questions=$(python3 -c "
import json, sys
tasks = json.load(open('$ROOT/plugin_tasks.json'))['tasks']['$domain'][:$n]
lines = ['/archcore:context $domain', '']
lines.append('For each question below, output ONLY the exact token value (one per line, in order):')
for i, t in enumerate(tasks, 1):
    lines.append(f\"{i}. {t['question']}\")
print('\n'.join(lines))
")
  echo "$questions"
}

# Build batch prompt for C-arm: N questions, no context load
build_c_prompt () {
  local domain="$1" n="$2"
  python3 -c "
import json
tasks = json.load(open('$ROOT/plugin_tasks.json'))['tasks']['$domain'][:$n]
lines = ['For each question below, output ONLY the exact token value (one per line, in order):']
for i, t in enumerate(tasks, 1):
    lines.append(f\"{i}. {t['question']}\")
print('\n'.join(lines))
"
}

# Grade multi-answer response: count how many expected tokens appear in the result
grade_batch () {
  local result="$1" domain="$2" n="$3"
  python3 -c "
import json, sys
tasks = json.load(open('$ROOT/plugin_tasks.json'))['tasks']['$domain'][:$n]
result = open('$result').read() if '$result'.endswith('.json') else '$result'
try:
    import json as j
    data = j.load(open('$result'))
    text = (data.get('result') or '').lower()
except:
    text = ''
correct = sum(1 for t in tasks if t['answer_token'].lower() in text)
print(f'{correct}/{len(tasks)}')
"
}

run_one () {
  local n="$1" domain="$2" arm="$3" trial="$4" prompt="$5"
  local out="$RAW/batch${n}_${domain}_${arm}_t${trial}.json"

  local attempt=0 ok=0
  while [ "$attempt" -le "$RETRIES" ]; do
    attempt=$((attempt + 1))
    : > "$out"

    local plugin_flag=""
    [ "$arm" = "D" ] && plugin_flag="--plugin-dir $PLUGIN"

    START_MS=$(python3 -c "import time; print(int(time.time()*1000))")
    # shellcheck disable=SC2086
    ( cd "$WORKDIR" && exec claude -p "$prompt" \
        $plugin_flag \
        --model "$MODEL" --output-format json \
        --strict-mcp-config --mcp-config "$MCP" \
        --dangerously-skip-permissions \
        --allowedTools $TOOLS \
        --max-turns "$MAXTURNS" < /dev/null ) > "$out" 2>/dev/null &
    local cpid=$!
    ( sleep "$TIMEOUT"; kill -TERM "$cpid" 2>/dev/null; sleep 3; kill -KILL "$cpid" 2>/dev/null ) &
    local wpid=$!
    wait "$cpid" 2>/dev/null || true
    kill "$wpid" 2>/dev/null || true
    wait "$wpid" 2>/dev/null || true
    END_MS=$(python3 -c "import time; print(int(time.time()*1000))")
    DUR_MS=$((END_MS - START_MS))

    if jq -e . "$out" >/dev/null 2>&1; then ok=1; break; fi
    echo "  retry batch${n} ${domain} ${arm} t${trial} (attempt $attempt)"
  done

  if [ "$ok" = "1" ]; then
    # Grade: count correct answers
    local grade
    grade=$(python3 -c "
import json
tasks = json.load(open('$ROOT/plugin_tasks.json'))['tasks']['$domain'][:$n]
data = json.load(open('$out'))
text = (data.get('result') or '').lower()
correct = sum(1 for t in tasks if t['answer_token'].lower() in text)
print(f'{correct},{len(tasks)},{correct/len(tasks):.4f}')
")
    jq -r --arg n "$n" --arg dom "$domain" --arg arm "$arm" --arg tr "$trial" \
       --arg grade "$grade" --arg dur "$DUR_MS" '
      [$n,$dom,$arm,$tr] + ($grade | split(",")) +
      [(.usage.input_tokens//0),(.usage.cache_creation_input_tokens//0),
       (.usage.cache_read_input_tokens//0),(.usage.output_tokens//0),
       (.total_cost_usd//0),(.num_turns//0),$dur,
       (if .is_error then 1 else 0 end)] | @csv' "$out" >> "$CSV"
    echo "  batch${n} ${domain} ${arm} t${trial} grade=$grade"
  else
    printf '"%s","%s","%s","%s",0,%s,0,0,0,0,0,0,0,0,1\n' \
      "$n" "$domain" "$arm" "$trial" "$n" >> "$CSV"
    echo "  batch${n} ${domain} ${arm} t${trial} TIMEOUT/CRASH"
  fi
}

echo "=== Plugin benchmark: N=80, domains=[$DOMAINS], batch_sizes=[$BATCH_SIZES], trials=$TRIALS ==="

for n in $BATCH_SIZES; do
  for domain in $DOMAINS; do
    for trial in $(seq 1 "$TRIALS"); do
      # Interleave D and C arms to decorrelate cache state
      for arm in D C; do
        if [ "$arm" = "D" ]; then
          prompt=$(build_d_prompt "$domain" "$n")
        else
          prompt=$(build_c_prompt "$domain" "$n")
        fi
        run_one "$n" "$domain" "$arm" "$trial" "$prompt"
      done
    done
  done
done

echo "=== done -> $CSV ==="

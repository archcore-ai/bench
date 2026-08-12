#!/usr/bin/env bash
# Plugin benchmark driver, v7 — rewritten for Archcore plugin v0.7.x.
#
# WHY THIS IS A NEW FILE (and not an edit of run_plugin.sh):
#   run_plugin.sh measures a mechanism that no longer exists. Through plugin v0.6 the
#   D-arm prompt opened with `/archcore:context <domain>`, an explicit retrieval command
#   that pulled the area's docs into the session up front. In v0.7.x that command is gone
#   (commands are now document/init/plan/review) and context arrives a different way: a
#   SessionStart hook injects a corpus header (doc counts, branch, tag vocabulary, a
#   pointer to the MCP tools) into every session automatically — roughly 150 tokens, and
#   no document bodies. run_plugin.sh is kept as-is so the v1/v2 numbers stay reproducible.
#
# What this measures now:
#   D-arm: plugin loaded (--plugin-dir) => SessionStart auto-injection + skills + hooks
#   C-arm: no plugin, same archcore MCP server (control)
#   Both arms get the SAME prompt. That is the design: in v0.7 the plugin's contribution is
#   ambient (injected context), not prompt-level, so any delta is attributable to it alone.
#
# Output: scale/results/plugin_results_v7.csv
# Usage:  PLUGIN=/path/to/plugin bash scale/run_plugin_v7.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH="$ROOT/scale"
MODEL="${MODEL:-sonnet}"
MAXTURNS="${MAXTURNS:-30}"
TIMEOUT="${TIMEOUT:-300}"
RETRIES="${RETRIES:-2}"
TRIALS="${TRIALS:-3}"
BATCH_SIZES="${BATCH_SIZES:-1 2 4 8}"
DOMAINS="${DOMAINS:-middleware routing errors logging testing}"
RESULTS="$BENCH/results"
RAW="$RESULTS/raw_plugin_v7"
CSV="${CSV:-$RESULTS/plugin_results_v7.csv}"

# PLUGIN: path to the archcore plugin. v0.7 restructured the repo into a marketplace layout
# (plugins/archcore/.claude-plugin/plugin.json); v0.6 and earlier had the manifest at the repo
# root. Accept either and resolve to the directory --plugin-dir actually needs.
resolve_plugin () {
  local p="$1"
  if [ -f "$p/plugins/archcore/.claude-plugin/plugin.json" ]; then echo "$p/plugins/archcore"; return; fi
  if [ -f "$p/.claude-plugin/plugin.json" ]; then echo "$p"; return; fi
  return 1
}
if [ -z "${PLUGIN:-}" ]; then
  PLUGIN="$(cd "$ROOT/.." && pwd)/plugin"
fi
PLUGIN_DIR="$(resolve_plugin "$PLUGIN")" || {
  echo "ERROR: no plugin manifest under $PLUGIN"
  echo "  expected $PLUGIN/plugins/archcore/.claude-plugin/plugin.json (v0.7+)"
  echo "        or $PLUGIN/.claude-plugin/plugin.json (v0.6 and earlier)"
  exit 1
}
PLUGIN_VER="$(python3 -c "import json;print(json.load(open('$PLUGIN_DIR/.claude-plugin/plugin.json'))['version'])")"

# The v0.7-conformant N=80 arm: same 80 docs and the same buried answer tokens as the CLI
# benchmark's C arm, with four uppercase acronym tags lowercased so `archcore status` reports
# a clean project. Verified: all 80 fact tokens and all 40 plugin-task tokens survive.
WORKDIR="${WORKDIR:-$BENCH/arms/N80v7/repo}"
MCP="$BENCH/arms/N80v7/mcp.json"
[ -d "$WORKDIR/.archcore" ] || { echo "ERROR: no .archcore in $WORKDIR — build the arm first"; exit 1; }
cat > "$MCP" <<EOF
{"mcpServers":{"archcore":{"command":"archcore","args":["mcp","--project","$WORKDIR"]}}}
EOF

# D also allows the plugin-prefixed tool names: when the plugin's own bundled MCP config
# loads, the same server is exposed as mcp__plugin_archcore_archcore__*. Allowing both means
# D is never blocked on a tool-name technicality; it does not give D extra capability.
C_TOOLS="Read Grep Glob mcp__archcore__search_documents mcp__archcore__get_document mcp__archcore__list_documents"
D_TOOLS="$C_TOOLS mcp__plugin_archcore_archcore__search_documents mcp__plugin_archcore_archcore__get_document mcp__plugin_archcore_archcore__list_documents"

mkdir -p "$RAW"

HDR="batch_size,domain,arm,trial,n_correct,n_total,pass_rate,input_tokens,cache_creation,cache_read,output_tokens,total_cost_usd,num_turns,duration_ms,is_error"
echo "$HDR" > "$CSV"

# Identical prompt for both arms — see header.
build_prompt () {
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

run_one () {
  local n="$1" domain="$2" arm="$3" trial="$4" prompt="$5"
  local out="$RAW/batch${n}_${domain}_${arm}_t${trial}.json"

  local attempt=0 ok=0
  while [ "$attempt" -le "$RETRIES" ]; do
    attempt=$((attempt + 1))
    : > "$out"

    local plugin_flag="" tools="$C_TOOLS"
    if [ "$arm" = "D" ]; then plugin_flag="--plugin-dir $PLUGIN_DIR"; tools="$D_TOOLS"; fi

    START_MS=$(python3 -c "import time; print(int(time.time()*1000))")
    # shellcheck disable=SC2086
    ( cd "$WORKDIR" && exec claude -p "$prompt" \
        $plugin_flag \
        --model "$MODEL" --output-format json \
        --strict-mcp-config --mcp-config "$MCP" \
        --dangerously-skip-permissions \
        --allowedTools $tools \
        --max-turns "$MAXTURNS" < /dev/null ) > "$out" 2>/dev/null &
    local cpid=$!
    ( sleep "$TIMEOUT"; kill -TERM "$cpid" 2>/dev/null; sleep 3; kill -KILL "$cpid" 2>/dev/null ) &
    local wpid=$!
    wait "$cpid" 2>/dev/null || true
    kill "$wpid" 2>/dev/null || true
    wait "$wpid" 2>/dev/null || true
    END_MS=$(python3 -c "import time; print(int(time.time()*1000))")
    DUR_MS=$((END_MS - START_MS))

    if jq -e . "$out" >/dev/null 2>&1; then
      # A 403/429/5xx comes back as valid JSON with .api_error_status set and zero usage.
      # Retry those with linear backoff — do NOT record them as real rows. Max-turns
      # flailing does NOT set api_error_status, so a genuinely expensive run still lands.
      apistat=$(jq -r '.api_error_status // empty' "$out")
      if [ -n "$apistat" ]; then
        echo "  api_error $apistat batch${n} ${domain} ${arm} t${trial} (attempt $attempt) — backoff $((30 * attempt))s"
        sleep $((30 * attempt))
        continue
      fi
      ok=1; break
    fi
    echo "  retry batch${n} ${domain} ${arm} t${trial} (attempt $attempt)"
  done

  if [ "$ok" = "1" ]; then
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
    echo "  batch${n} ${domain} ${arm} t${trial} grade=$grade turns=$(jq -r '.num_turns' "$out")"
  else
    printf '"%s","%s","%s","%s",0,%s,0,0,0,0,0,0,0,0,1\n' \
      "$n" "$domain" "$arm" "$trial" "$n" >> "$CSV"
    echo "  batch${n} ${domain} ${arm} t${trial} TIMEOUT/CRASH"
  fi
}

echo "=== Plugin benchmark v7 ==="
echo "  plugin:   $PLUGIN_DIR (v$PLUGIN_VER)"
echo "  cli:      $(archcore --version 2>&1 | tail -1)"
echo "  claude:   $(claude --version)"
echo "  workdir:  $WORKDIR ($(find "$WORKDIR/.archcore" -name '*.md' | wc -l | tr -d ' ') docs)"
echo "  matrix:   domains=[$DOMAINS] batch=[$BATCH_SIZES] trials=$TRIALS"

for n in $BATCH_SIZES; do
  for domain in $DOMAINS; do
    for trial in $(seq 1 "$TRIALS"); do
      prompt=$(build_prompt "$domain" "$n")
      # Interleave D and C back-to-back on the same prompt to decorrelate cache state.
      for arm in D C; do
        run_one "$n" "$domain" "$arm" "$trial" "$prompt"
        [ "${GAP:-0}" -gt 0 ] && sleep "$GAP"
      done
    done
  done
done

echo "=== done -> $CSV ==="

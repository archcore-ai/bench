#!/usr/bin/env bash
# Scale benchmark driver: crossover (cost vs KB size, fixed task) + workload (fixed big KB, task suite).
# Arms: A=cold, B1=preload(CLAUDE.md), B2=index+grep(.archcore files), C=archcore(MCP).
# Emits exact API usage + a pass/fail grade per run to a CSV. Arm order is randomized per unit
# (deterministically, by seed) to decorrelate prompt-cache state from the arm.
#
# Usage: run.sh [crossover|workload|all]
# Env knobs: MODEL XTRIALS WTRIALS XSIZES WSIZE MAXTURNS CSV FRESH
set -euo pipefail

BENCH="$(cd "$(dirname "$0")" && pwd)"
MODEL="${MODEL:-sonnet}"
PHASE="${1:-all}"
XTRIALS="${XTRIALS:-5}"
WTRIALS="${WTRIALS:-3}"
XSIZES="${XSIZES:-1 20 80 160 320}"
WSIZE="${WSIZE:-80}"
MAXTURNS="${MAXTURNS:-12}"
TIMEOUT="${TIMEOUT:-180}"   # per-call wall-clock cap (s); a wedged claude -p is killed, not left to block
RETRIES="${RETRIES:-1}"     # extra attempts when a call times out / yields no valid JSON
RESULTS="$BENCH/results"
RAW="$RESULTS/raw"
CSV="${CSV:-$RESULTS/results.csv}"
FRESH="${FRESH:-1}"
ARMS_DIR="$BENCH/arms"
mkdir -p "$RAW"

HDR="phase,N,task_id,arm,trial,pass,input_tokens,cache_creation,cache_read,output_tokens,total_cost_usd,num_turns,duration_ms,is_error,subtype"
if [ "$FRESH" = "1" ] || [ ! -f "$CSV" ]; then echo "$HDR" > "$CSV"; fi

READ_TOOLS=(Read Grep Glob)
C_TOOLS=(Read Grep Glob mcp__archcore__search_documents mcp__archcore__get_document mcp__archcore__list_documents)

# deterministic per-unit arm permutation (decorrelates cache state from arm)
# arm_order <seed-key> <space-separated arm set>
arm_order () { python3 -c "import sys,random;r=random.Random(sys.argv[1]);a=sys.argv[2].split();r.shuffle(a);print(' '.join(a))" "$1" "$2"; }

build_n () { # build all four arm dirs for KB size N (idempotent per N), + C's mcp config
  local n="$1"                      # assign before referencing (set -u safe; no reliance on a stray global)
  local base="$ARMS_DIR/N${n}" arm
  for arm in A B1 B2 B3 C; do
    [ -f "$base/$arm/repo/go.mod" ] || python3 "$BENCH/build_arm.py" "$arm" "$n" "$base/$arm/repo" >/dev/null
  done
  cat > "$base/mcp-C.json" <<EOF
{"mcpServers":{"archcore":{"command":"archcore","args":["mcp","--project","$base/C/repo"]}}}
EOF
}

run_one () { # phase N task_id arm trial question token
  local phase="$1" n="$2" tid="$3" arm="$4" trial="$5" question="$6" token="$7"
  local base="$ARMS_DIR/N${n}" workdir mcp out
  workdir="$base/$arm/repo"
  local allowed=("${READ_TOOLS[@]}")
  if [ "$arm" = "C" ]; then mcp="$base/mcp-C.json"; allowed=("${C_TOOLS[@]}"); else mcp="$BENCH/mcp-empty.json"; fi
  out="$RAW/${phase}_N${n}_${tid}_${arm}_t${trial}.json"

  # Run claude with a per-call watchdog + retry. exec => the bg PID *is* claude (no orphan);
  # </dev/null => no stdin wait; reap any straggler MCP child after each attempt.
  local attempt=0 ok=0
  while [ "$attempt" -le "$RETRIES" ]; do
    attempt=$((attempt + 1))
    : > "$out"
    ( cd "$workdir" && exec claude -p "$question" \
        --model "$MODEL" --output-format json \
        --strict-mcp-config --mcp-config "$mcp" \
        --dangerously-skip-permissions \
        --disallowedTools Write Edit MultiEdit NotebookEdit \
        --allowedTools "${allowed[@]}" \
        --max-turns "$MAXTURNS" < /dev/null ) > "$out" 2>/dev/null &
    local cpid=$!
    ( sleep "$TIMEOUT"; kill -TERM "$cpid" 2>/dev/null; sleep 3; kill -KILL "$cpid" 2>/dev/null ) &
    local wpid=$!
    # guard under `set -e`: a killed claude / already-exited watchdog returns non-zero.
    wait "$cpid" 2>/dev/null || true     # claude exit (0, non-zero, or killed by watchdog)
    kill "$wpid" 2>/dev/null || true     # stop the watchdog if it's still sleeping
    wait "$wpid" 2>/dev/null || true
    # claude's exit closes the MCP stdio pipe -> the archcore stdio server exits on its own
    # (verified: prior runs left no bench MCP orphans). No pkill needed.
    if jq -e . "$out" >/dev/null 2>&1; then ok=1; break; fi
    echo "  retry $phase N=$n $tid $arm t$trial (attempt $attempt: timeout/no-json)"
  done

  if [ "$ok" = "1" ]; then
    local pass; pass=$(python3 "$BENCH/grade.py" "$out" "$token")
    jq -r --arg ph "$phase" --arg n "$n" --arg tid "$tid" --arg arm "$arm" --arg tr "$trial" --arg pass "$pass" '
      [$ph,$n,$tid,$arm,$tr,$pass,
       (.usage.input_tokens//0),(.usage.cache_creation_input_tokens//0),
       (.usage.cache_read_input_tokens//0),(.usage.output_tokens//0),
       (.total_cost_usd//0),(.num_turns//0),(.duration_ms//0),
       (if .is_error then 1 else 0 end),(.subtype//"")] | @csv' "$out" >> "$CSV"
    local err; err=$(jq -r '(if .is_error then "ERR:"+(.subtype//"?") else "" end)' "$out" 2>/dev/null || echo "")
    echo "  $phase N=$n $tid $arm t$trial pass=$pass $err"
  else
    # killed/crashed on every attempt -> synthetic failure row so the cell is never silently missing
    printf '"%s","%s","%s","%s","%s",0,0,0,0,0,0,0,0,1,"timeout"\n' "$phase" "$n" "$tid" "$arm" "$trial" >> "$CSV"
    echo "  $phase N=$n $tid $arm t$trial pass=0 TIMEOUT/CRASH (after $((RETRIES+1)) attempts)"
  fi
}

# task tuples: anchor (crossover) = row 0; workload = rows 0,4,8,...,76
read_anchor () { python3 -c "import csv;r=list(csv.DictReader(open('$BENCH/facts.csv')));x=r[0];print(x['doc_id']+'\t'+x['question']+'\t'+x['answer_token'])"; }
write_workload_tsv () { python3 -c "
import csv,sys
wsize=int(sys.argv[1]); ntasks=20
r=list(csv.DictReader(open('$BENCH/facts.csv')))
# ~20 tasks drawn from the first wsize docs (so every target exists in the N=wsize KB), span domains
step=max(1, wsize//ntasks)
for i in range(0, wsize, step):
    x=r[i]; print(x['doc_id']+'\t'+x['question']+'\t'+x['answer_token'])
" "$WSIZE" > "$BENCH/tasks_workload.tsv"; }

do_crossover () {
  IFS=$'\t' read -r A_ID A_Q A_TOK < <(read_anchor)
  echo "== crossover: anchor task $A_ID, sizes [$XSIZES], $XTRIALS trials =="
  for n in $XSIZES; do
    build_n "$n"
    for trial in $(seq 1 "$XTRIALS"); do
      for arm in $(arm_order "x-$n-$trial" "A B1 B2 B3 C"); do
        run_one crossover "$n" "$A_ID" "$arm" "$trial" "$A_Q" "$A_TOK"
      done
    done
  done
}

do_workload () {
  write_workload_tsv
  echo "== workload: N=$WSIZE, $(wc -l < "$BENCH/tasks_workload.tsv" | tr -d ' ') tasks, $WTRIALS trials =="
  build_n "$WSIZE"
  while IFS=$'\t' read -r tid q tok; do
    for trial in $(seq 1 "$WTRIALS"); do
      # workload = the equal-quality cost race over realistic on-demand baselines.
      # B2=index+grep, B3=blind grep, C=archcore. A (always fails) + B1 (preload, shown in
      # crossover) are omitted here to bound runs.
      for arm in $(arm_order "w-$tid-$trial" "B2 B3 C"); do
        run_one workload "$WSIZE" "$tid" "$arm" "$trial" "$q" "$tok"
      done
    done
  done < "$BENCH/tasks_workload.tsv"
}

case "$PHASE" in
  crossover) do_crossover ;;
  workload)  do_workload ;;
  all)       do_crossover; do_workload ;;
  *) echo "unknown phase: $PHASE"; exit 1 ;;
esac
echo "=== done -> $CSV ==="
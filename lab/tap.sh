#!/bin/bash
# usage: tap.sh <label> <file.shortcut basename> <shortcut name>
# Tries import methods in order (https localhost w/ trusted test CA, plain http, Files app tap),
# taps through Add, then taps the library tile to run it.
set -u
L=$1; F=$2; N=$3
U=$(cat "$OUT/udid.txt"); S="$OUT/screens/$L"; mkdir -p "$S" "$OUT/hier"
M() { local log=$1; shift; local t0=$SECONDS; perl -e 'alarm 300; exec @ARGV' maestro --device "$U" "$@" > "$OUT/maestro-$L-$log.log" 2>&1; local rc=$?; echo "  maestro $log exit=$rc $((SECONDS-t0))s"; return $rc; }
enc() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1"; }
shot() { xcrun simctl io "$U" screenshot "$S/$1.png" >/dev/null 2>&1; }
hier() { perl -e 'alarm 120; exec @ARGV' maestro --device "$U" hierarchy > "$OUT/hier/$L-$1.json" 2>/dev/null
  python3 - "$OUT/hier/$L-$1.json" <<'PY'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception as e: print("  (no hierarchy)"); sys.exit()
seen=[]
def w(n):
    a=n.get("attributes",{}); v=a.get("text") or a.get("accessibilityText")
    if v and v not in seen and v!="0%": seen.append(v)
    for c in n.get("children",[]): w(c)
w(d); print("  labels:", seen[:40])
PY
}
step() { echo "STEP $L: $1 => $2" | tee -a "$OUT/steps.txt"; }
ok=0; i=0
P=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$F")
for method in https http files; do
  i=$((i+1)); echo "=== [$L] import via $method"
  case $method in
    https) xcrun simctl openurl "$U" "shortcuts://import-shortcut?url=$(enc "https://localhost:8443/$P")&name=$(enc "$N")" ;;
    http)  xcrun simctl openurl "$U" "shortcuts://import-shortcut?url=$(enc "http://127.0.0.1:8765/$P")&name=$(enc "$N")" ;;
    files) M files-open test -e STEM="${F%.shortcut}" -e FILE="$F" "$GITHUB_WORKSPACE/lab/flows/open_in_files.yaml" ;;
  esac
  sleep 10; shot "$i-$method-1-import"; hier "$i-$method-import"
  M "$method-accept" test "$GITHUB_WORKSPACE/lab/flows/accept.yaml"
  shot "$i-$method-2-after-add"
  if M "$method-run" test -e NAME="$N" "$GITHUB_WORKSPACE/lab/flows/run_tile.yaml"; then
    step "import($method)+add" PASS; step tap-tile-run PASS; ok=1
    sleep 3; shot "$i-$method-3-after-tap"; hier "$i-$method-after-tap"
    M "$method-accept2" test "$GITHUB_WORKSPACE/lab/flows/accept.yaml"
    sleep 6; shot "$i-$method-4-after-prompts"; hier "$i-$method-after-prompts"
    M "$method-accept3" test "$GITHUB_WORKSPACE/lab/flows/accept.yaml"
    sleep 4; shot "$i-$method-5-final"
    break
  else
    step "import($method)+add" FAIL
    M "$method-dismiss" test "$GITHUB_WORKSPACE/lab/flows/accept.yaml"
  fi
done
[ $ok = 1 ] || step tap-tile-run "SKIPPED (no import method worked)"
true

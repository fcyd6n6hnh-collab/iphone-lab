#!/bin/bash
# usage: tap.sh <label> <file.shortcut basename> <shortcut name>
# Imports a signed shortcut from the local HTTP server, taps through Add, then taps the tile to run it.
set -u
L=$1; F=$2; N=$3
U=$(cat "$OUT/udid.txt"); S="$OUT/screens/$L"; mkdir -p "$S" "$OUT/hier"
enc() { python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1"; }
shot() { xcrun simctl io "$U" screenshot "$S/$1.png" >/dev/null 2>&1; echo "  screenshot $L/$1.png"; }
hier() { perl -e 'alarm 120; exec @ARGV' maestro --device "$U" hierarchy > "$OUT/hier/$L-$1.json" 2>/dev/null; python3 - "$OUT/hier/$L-$1.json" <<'PY'
import json,sys
try: d=json.load(open(sys.argv[1]))
except Exception as e: print("  (no hierarchy:",e,")"); sys.exit()
seen=[]
def w(n):
    a=n.get("attributes",{})
    for k in ("text","accessibilityText","title"):
        v=a.get(k)
        if v and v not in seen: seen.append(v)
    for c in n.get("children",[]): w(c)
w(d); print("  visible labels:", seen[:60])
PY
}
step() { echo "STEP $L: $1 => $2" | tee -a "$OUT/steps.txt"; }

echo "=== [$L] import $N"
URL="http://127.0.0.1:8765/$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$F")"
curl -sf -o /dev/null "$URL" && step import-file-served PASS || step import-file-served FAIL
xcrun simctl openurl "$U" "shortcuts://import-shortcut?url=$(enc "$URL")&name=$(enc "$N")"; echo "openurl exit=$?"
sleep 12; shot 01-import-sheet; hier 01-import
perl -e 'alarm 240; exec @ARGV' maestro --device "$U" test "$GITHUB_WORKSPACE/lab/flows/accept.yaml" > "$OUT/maestro-$L-accept1.log" 2>&1; echo "maestro accept1 exit=$?"
sleep 3; shot 02-after-add; hier 02-after-add

echo "=== [$L] run by tapping tile"
perl -e 'alarm 240; exec @ARGV' maestro --device "$U" test -e NAME="$N" "$GITHUB_WORKSPACE/lab/flows/run_tile.yaml" > "$OUT/maestro-$L-run.log" 2>&1
rc=$?; [ $rc = 0 ] && step tap-tile PASS || step tap-tile "FAIL(maestro exit $rc)"
sleep 4; shot 03-after-tap; hier 03-after-tap
perl -e 'alarm 240; exec @ARGV' maestro --device "$U" test "$GITHUB_WORKSPACE/lab/flows/accept.yaml" > "$OUT/maestro-$L-accept2.log" 2>&1; echo "maestro accept2 exit=$?"
sleep 8; shot 04-after-prompts; hier 04-after-prompts
if [ $rc != 0 ]; then
  echo "=== [$L] fallback: run via URL scheme"
  xcrun simctl openurl "$U" "shortcuts://run-shortcut?name=$(enc "$N")"
  sleep 8; shot 05-url-run
  perl -e 'alarm 240; exec @ARGV' maestro --device "$U" test "$GITHUB_WORKSPACE/lab/flows/accept.yaml" > "$OUT/maestro-$L-accept3.log" 2>&1
  sleep 8; shot 06-url-run-after-prompts; hier 06-url-run
fi

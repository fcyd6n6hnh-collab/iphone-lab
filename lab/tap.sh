#!/bin/bash
# usage: tap.sh <label> <file.shortcut basename> <shortcut name>
# Files-app import + tap-through in ONE Maestro session (shortcuts://import-shortcut rejects non-iCloud URLs).
set -u
L=$1; F=$2; N=$3
U=$(cat "$OUT/udid.txt"); S="$OUT/screens/$L"; mkdir -p "$S" "$OUT/hier"
step() { echo "STEP $L: $1 => $2" | tee -a "$OUT/steps.txt"; }
t0=$SECONDS
perl -e 'alarm 900; exec @ARGV' maestro --device "$U" test -e FILE="$F" -e NAME="$N" -e SHOTS="$S" \
  "$GITHUB_WORKSPACE/lab/flows/full.yaml" > "$OUT/maestro-$L-full.log" 2>&1; rc=$?
echo "maestro full exit=$rc $((SECONDS-t0))s"; tail -40 "$OUT/maestro-$L-full.log"
xcrun simctl io "$U" screenshot "$S/08-sim-final.png" >/dev/null 2>&1
g() { grep -q "$1" "$OUT/maestro-$L-full.log"; }
g 'Tap on "'"$F"'"... COMPLETED' && step files-tap-file PASS || step files-tap-file FAIL
g 'Tap on "Add Shortcut"... COMPLETED' && step tap-add-shortcut PASS || step tap-add-shortcut "FAIL/not shown"
g 'Tap on "'"$N"'"... COMPLETED' && step tap-library-tile PASS || step tap-library-tile FAIL
for b in "Always Allow" "Allow Once" "Turn On All" "Allow"; do g "Tap on \"$b\"... COMPLETED" && step "prompt '$b' tapped" yes; done
perl -e 'alarm 120; exec @ARGV' maestro --device "$U" hierarchy > "$OUT/hier/$L-final.json" 2>/dev/null
true

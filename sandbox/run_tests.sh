#!/bin/sh
# each tests/*.plist has one injected fault; all must FAIL
cd "$(dirname "$0")"; ok=0
for f in tests/*.plist; do if python3 sbx.py validate "$f" >/dev/null; then echo "MISSED: $f"; ok=1; else echo "caught: $f"; fi; done
exit $ok

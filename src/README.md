v2 rebuild (2026-10-21). Build: /workspace/.venv-sk/bin/python v2/build_v2.py ; validate: v2/validate.py ; sign: v2/sign_v2.py
Signed outputs: ../Health Test.shortcut, ../Health Sync v2.shortcut, ../Grok Inbox v2.shortcut
Reference real exports (iCloud API): ../ref/*.shortcut ; validator report: validate_v2.txt ; Cherri decompiles: roundtrip/
Signed payloads extracted with shortcut-sign: extracted/  (identical to submitted except WFWorkflowClientVersion -> 1505.3)

## Health Sync v3 (2026-10-21)
Mail-free. Find Health Samples (exact 4ee674 copy) -> Repeat: Get Details of Health Sample (Start Date, End Date, Value, Duration) -> Text "start - end value duration" -> End Repeat -> Combine Text (new lines) -> Get Contents of URL POST https://ntfy.sh, JSON body {topic: <topic>-h, title: health-sync, message: "Sleep samples (last 1 day):\n<lines>"} (shape from brrr 7ada1993).
Built by build_v3.py, signed by sign_v3.py. validate.py PASS pre/post signing; shortcut-sign verify OK. NOTE: ntfy rejects JSON messages > 4096 bytes (HTTP 500), i.e. roughly 80+ samples.

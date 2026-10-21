# iphone-sandbox — test Apple Shortcuts on Linux before they go to the phone

    ./sbx.py validate FILE...          # Apple-schema checks (signed AEA or unsigned plist)
    ./sbx.py run FILE [--mocks m.json] # dry-run with mock Health / Reminders / Mail / URL / battery
    ./sbx.py dump FILE                 # decoded plist as JSON
    ./run_tests.sh                     # injected-fault regression tests

Schema source: Apple's own iOS 27.0.1 (24A446, iPhone17,1) restore image from updates.cdn-apple.com.
  tools/dsc_strings.py   pulls WorkflowKit/ActionKit/ContentKit string tables out of the dyld_shared_cache
                         (works even though .dyldlinkedit/.symbols are lzbitmap-compressed and unreadable on Linux)
  tools/build_schema.py  -> schema/apple_ios27.json: 402 is.workflow.actions.* ids, ~12.5k framework strings,
                         6.5k WF* tokens, 46 link.contentkit.* serialized keys, 1,472 system App Intents with
                         parameter names, real parameter shapes from Apple Gallery .wflow + ref exports.
Raw firmware extracts: /workspace/ipsw-work (dyld cache ~5.4 GB, extracted frameworks, fs-list.txt).

Validator checks: action id exists in iOS 27; parameter keys exist in Apple binaries or a real export
(<=15-byte keys only WARN: Swift inlines short strings); WFSerializationType names exist; SerializedEntry keys
are real link.contentkit.* keys; attachmentsByRange UTF-16 offsets hit U+FFFC and counts match; OutputUUID
references point to an earlier action; control-flow blocks open/close and nest; shapes vs real exports (WARN).

Limits: not Apple's runtime. No iOS UI, permissions, Focus, or real HealthKit. ~40 common actions are simulated;
others are logged as NOT SIMULATED. A PASS means "no known structural fault", not "will run". Final check is the phone.

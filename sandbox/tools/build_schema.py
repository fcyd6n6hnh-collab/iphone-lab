"""Build schema/apple_ios27.json from Apple's own iOS 27.0.1 (24A446) firmware artifacts:
  - WorkflowKit / ActionKit / ContentKit string tables pulled from the dyld_shared_cache (dsc_strings.py)
  - link.contentkit.* serialized keys found anywhere in the cache
  - every Metadata.appintents/extract.actionsdata (App Intents action ids + parameter names)
  - Apple's Gallery.bundle *.wflow shortcuts (real Apple-authored action parameter shapes)
plus real user exports in /workspace/iphone-shortcuts/ref (iCloud API downloads) as extra shape examples."""
import json, glob, plistlib, re, os, subprocess
IPSW = '/workspace/ipsw-work'
OUT = '/workspace/iphone-sandbox/schema/apple_ios27.json'
S = {}
for L in ('WorkflowKit', 'ActionKit', 'ContentKit'):
    S[L] = set(open(f'{IPSW}/dylibs/{L}.strings.txt').read().split('\n'))
allstr = set().union(*S.values())
action_ids = sorted(s for s in allstr if re.fullmatch(r'is\.workflow\.actions\.[A-Za-z0-9_.\-]+', s))
wf_tokens = sorted(s for s in allstr if re.fullmatch(r'[A-Za-z][A-Za-z0-9_.]{1,80}', s))
ser_types = sorted(s for s in allstr if re.fullmatch(r'WF[A-Za-z]+(SubstitutableState|Value|TokenString|TokenAttachment|Template|FieldValue)', s))
cache = f'{IPSW}/sysos/x/System/Library/Caches/com.apple.dyld'
ck = subprocess.run(f"rg -a -o -N --no-filename 'link\\.contentkit\\.[a-z.]+' {cache}", shell=True, capture_output=True, text=True).stdout.split()
contentkit_keys = sorted(set(ck))
cache_wf = sorted(set(subprocess.run(f"rg -a -o -N --no-filename '\\bWF[A-Za-z0-9_]{{2,80}}' {cache}", shell=True, capture_output=True, text=True).stdout.split()))
# App Intents
intents = {}
for f in glob.glob(f'{IPSW}/fs/**/Metadata.appintents/extract.actionsdata', recursive=True):
    try: d = json.load(open(f))
    except Exception: continue
    bundle = f.split('/Metadata.appintents')[0].split('/')[-1]
    for aid, a in (d.get('actions') or {}).items():
        params = [p.get('name') for p in a.get('parameters', []) if isinstance(p, dict)]
        intents.setdefault(aid, {'bundles': [], 'parameters': sorted(set(filter(None, params)))})['bundles'].append(bundle)
# shapes from Apple gallery + refs
shapes = {}
def add_shapes(src, p):
    for a in p.get('WFWorkflowActions', []):
        shapes.setdefault(a['WFWorkflowActionIdentifier'], []).append({'src': src, 'params': a.get('WFWorkflowActionParameters', {})})
for f in glob.glob(f'{IPSW}/fs/System/Library/PrivateFrameworks/WorkflowKit.framework/Gallery.bundle/*.wflow'):
    add_shapes('apple-gallery:' + os.path.basename(f), plistlib.load(open(f, 'rb')))
for f in glob.glob('/workspace/iphone-shortcuts/ref/*.shortcut'):
    try: add_shapes('ref:' + os.path.basename(f)[:8], plistlib.load(open(f, 'rb')))
    except Exception: pass
for f in glob.glob('/workspace/shortcuts-playground-plugin/claude/skills/shortcuts-playground/golden-shortcuts/xml/*.xml'):
    try: add_shapes('golden:' + os.path.basename(f)[:12], plistlib.load(open(f, 'rb')))
    except Exception: pass
json.dump({'source': 'iPhone17,1 iOS 27.0.1 (24A446) Restore.ipsw, Apple CDN', 'action_ids': action_ids,
           'tokens': wf_tokens, 'serialization_types': ser_types, 'contentkit_keys': contentkit_keys, 'cache_wf_tokens': cache_wf,
           'app_intents': intents, 'shapes': shapes}, open(OUT, 'w'), default=lambda o: o.hex() if isinstance(o, bytes) else str(o))
print(len(action_ids), 'action ids;', len(wf_tokens), 'tokens;', len(ser_types), 'ser types;', len(contentkit_keys), 'contentkit keys;', len(cache_wf), 'WF* tokens in whole cache;', len(intents), 'app intents;', len(shapes), 'actions with real shapes')

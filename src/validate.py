"""Validate a Shortcuts plist two ways:
 1) shortcutkit 0.8.1: every action re-fed through Shortcut.action() (unknown identifier/keys, value kinds).
 2) Structural diff vs real Apple-exported shortcuts in ../ref (iCloud API downloads): for each action,
    every key path + value type must exist in at least one real export of the same identifier."""
import sys, glob, plistlib, json
sys.path.insert(0, '/workspace/.venv-sk/lib/python3.12/site-packages')
import shortcutkit as sk

REF = {}
for f in glob.glob('/workspace/iphone-shortcuts/ref/*.shortcut'):
    try: p = plistlib.load(open(f, 'rb'))
    except Exception: continue
    for a in p['WFWorkflowActions']:
        REF.setdefault(a['WFWorkflowActionIdentifier'], []).append((f.split('/')[-1][:8], a.get('WFWorkflowActionParameters', {})))
for f in glob.glob('/workspace/shortcuts-playground-plugin/claude/skills/shortcuts-playground/golden-shortcuts/xml/*.xml'):
    p = plistlib.load(open(f, 'rb'))
    for a in p['WFWorkflowActions']:
        REF.setdefault(a['WFWorkflowActionIdentifier'], []).append(('golden:' + f.split('/')[-1][:8], a.get('WFWorkflowActionParameters', {})))

IGNORE_VALUES = {'UUID', 'GroupingIdentifier', 'OutputUUID'}
def paths(obj, pre=''):
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            kk = k
            if k.startswith('{') and k.endswith('}'): kk = '{range}'      # attachmentsByRange keys
            out.add((pre + '/' + kk, type(v).__name__))
            out |= paths(v, pre + '/' + kk)
    elif isinstance(obj, list):
        for v in obj:
            out.add((pre + '[]', type(v).__name__)); out |= paths(v, pre + '[]')
    return out

def validate(path):
    p = plistlib.load(open(path, 'rb'))
    ok = True
    print(f'== {path}')
    s = sk.Shortcut('check')
    for n, a in enumerate(p['WFWorkflowActions']):
        ident = a['WFWorkflowActionIdentifier']; params = dict(a.get('WFWorkflowActionParameters', {}))
        params.pop('UUID', None)
        try:
            s.action(ident, **params); sk_res = 'ok'
        except Exception as e:
            sk_res = f'FAIL {e}'; ok = False
        refs = REF.get(ident, [])
        if not refs:
            diff = 'no real export to compare'
        else:
            mine = {x for x in paths(params)}
            allowed = set().union(*(paths(r) for _, r in refs))
            missing = sorted(m for m in mine if m not in allowed and not m[0].endswith(('CustomOutputName',)))
            if missing: ok = False
            diff = 'matches real exports' if not missing else f'NOT IN ANY REAL EXPORT: {missing}'
            diff += f' (refs: {", ".join(sorted({r for r, _ in refs})[:4])})'
        print(f'  [{n}] {ident}: shortcutkit={sk_res}; structure: {diff}')
    print('  RESULT:', 'PASS' if ok else 'FAIL')
    return ok

if __name__ == '__main__':
    r = [validate(x) for x in sys.argv[1:]]
    sys.exit(0 if all(r) else 1)

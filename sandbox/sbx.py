#!/usr/bin/env python3
"""iphone-sandbox: validate and dry-run Apple Shortcuts on Linux.

  sbx.py validate FILE...            check against Apple iOS 27.0.1 schemas (schema/apple_ios27.json)
  sbx.py run FILE [--mocks m.json]   simulate the shortcut with mock Health/Reminders/Mail/URL/battery
  sbx.py dump FILE                   print the decoded workflow plist as JSON

FILE may be a signed .shortcut (AEA1), an unsigned .shortcut / .wflow (binary or XML plist), or .plist.
Nothing leaves the box: email, reminders, notifications and web requests are all mocked unless
--live-get is passed (then plain HTTP GETs are performed for real)."""
import sys, os, json, plistlib, subprocess, re, argparse, datetime, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = json.load(open(os.path.join(HERE, 'schema/apple_ios27.json')))
ACTION_IDS = set(SCHEMA['action_ids']); TOK = set(SCHEMA['tokens']) | set(SCHEMA['cache_wf_tokens'])
CK_KEYS = set(SCHEMA['contentkit_keys']); INTENTS = SCHEMA['app_intents']; SHAPES = SCHEMA['shapes']
FFFC = '\ufffc'

# ---------------------------------------------------------------- loading
def load(path):
    b = open(path, 'rb').read()
    info = {'signed': False}
    if b[:4] == b'AEA1':
        info['signed'] = True
        info['signer_chain_present'] = b'SigningCertificateChain' in b[:20000] or b'Apple' in b[:20000]
        i = b.find(b'bvx')
        if i < 0: raise ValueError('signed shortcut: no LZFSE payload found')
        d = subprocess.run([os.path.expanduser('~/.local/bin/lzfse'), '-decode'], input=b[i:], capture_output=True).stdout
        j = d.find(b'bplist00')
        if not d.startswith(b'AA01') or j < 0: raise ValueError('signed shortcut: payload is not an Apple Archive with a plist')
        b = d[j:]
    return plistlib.loads(b), info

# ---------------------------------------------------------------- validation
class Report:
    def __init__(s): s.items = []
    def err(s, where, msg): s.items.append(('ERROR', where, msg))
    def warn(s, where, msg): s.items.append(('WARN', where, msg))
    def ok(s): return not any(l == 'ERROR' for l, _, _ in s.items)

def shape_paths(obj, pre=''):
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            kk = '{range}' if re.fullmatch(r'\{\d+, \d+\}', k) else k
            out.add((pre + '/' + kk, type(v).__name__)); out |= shape_paths(v, pre + '/' + kk)
    elif isinstance(obj, list):
        for v in obj: out.add((pre + '[]', type(v).__name__)); out |= shape_paths(v, pre + '[]')
    return out

def walk(obj, fn, path=''):
    fn(obj, path)
    if isinstance(obj, dict):
        for k, v in obj.items(): walk(v, fn, f'{path}/{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj): walk(v, fn, f'{path}[{i}]')

TOP = {'WFWorkflowActions': list, 'WFWorkflowClientVersion': str, 'WFWorkflowIcon': dict,
       'WFWorkflowImportQuestions': list, 'WFWorkflowInputContentItemClasses': list,
       'WFWorkflowMinimumClientVersion': int, 'WFWorkflowTypes': list}

def validate(p, r):
    for k, t in TOP.items():
        if k not in p: r.warn('top', f'missing {k} (Apple exports always include it)')
        elif not isinstance(p[k], t): r.err('top', f'{k} should be {t.__name__}, is {type(p[k]).__name__}')
    for k in p:
        if k not in TOK and not k.startswith('WF'): r.warn('top', f'unknown top-level key {k}')
        elif k not in TOK: r.warn('top', f'top-level key {k} not found in iOS 27 binaries')
    for c in p.get('WFWorkflowInputContentItemClasses', []):
        if c not in TOK: r.err('top', f'input content class {c} does not exist in iOS 27')
    uuids, groups = {}, {}
    for n, a in enumerate(p.get('WFWorkflowActions', [])):
        w = f'[{n}] {a.get("WFWorkflowActionIdentifier")}'
        ident = a.get('WFWorkflowActionIdentifier'); params = a.get('WFWorkflowActionParameters', {})
        if not isinstance(ident, str): r.err(w, 'missing WFWorkflowActionIdentifier'); continue
        if not isinstance(params, dict): r.err(w, 'WFWorkflowActionParameters is not a dict'); continue
        if ident.startswith('is.workflow.actions.'):
            if ident not in ACTION_IDS: r.err(w, 'action identifier not present in iOS 27 WorkflowKit/ActionKit')
        else:
            short = ident.split('.')[-1]
            if ident not in INTENTS and short not in INTENTS: r.warn(w, 'App Intent / third-party action not found in Apple system App Intents metadata (fine if it is a third-party app)')
        # parameter keys must be real Apple vocabulary or seen in a real export of this action
        real = SHAPES.get(ident, [])
        real_keys = set().union(*(set(x['params']) for x in real)) if real else set()
        intent_params = set((INTENTS.get(ident) or INTENTS.get(ident.split('.')[-1]) or {}).get('parameters', []))
        for k in params:
            if k in ('UUID', 'GroupingIdentifier', 'WFControlFlowMode', 'CustomOutputName', 'ShowWhenRun', 'AppIntentDescriptor'): continue
            if k.startswith('Show-') and (k[5:] in params or k[5:] in TOK): continue   # UI 'show more' flags, built at runtime
            if k not in TOK and k not in real_keys and k not in intent_params:
                if len(k.encode()) <= 15:   # Swift stores <=15-byte strings inline in code, so absence from string tables proves nothing
                    r.warn(w, f'parameter key "{k}" not found in iOS 27 string tables or real exports (short key: may be a Swift inline string, verify)')
                else:
                    r.err(w, f'parameter key "{k}" does not exist in iOS 27 binaries or any real export of this action')
        if real:
            mine = {m for m in shape_paths({k: v for k, v in params.items() if k != 'UUID'}) if not m[0].endswith(('CustomOutputName',))}
            allowed = set().union(*(shape_paths(x['params']) for x in real))
            miss = sorted(m for m in mine if m not in allowed)
            if miss: r.warn(w, f'shape not seen in {len(real)} real export(s): {miss[:4]}{" ..." if len(miss) > 4 else ""}')
        else:
            r.warn(w, 'no real Apple/ref export of this action to compare shapes against')
        if 'UUID' in params:
            if params['UUID'] in uuids: r.err(w, 'duplicate UUID')
            uuids[params['UUID']] = n
        if 'WFControlFlowMode' in params:
            g = params.get('GroupingIdentifier'); groups.setdefault(g, []).append((n, params['WFControlFlowMode'], ident))
        def check(v, path):
            if not isinstance(v, dict): return
            st = v.get('WFSerializationType')
            if st is not None and st not in TOK: r.err(w, f'{path}: WFSerializationType {st} does not exist in iOS 27')
            if 'SerializedEntry' in v:
                for sk in v['SerializedEntry']:
                    if sk not in CK_KEYS: r.err(w, f'{path}: SerializedEntry key "{sk}" does not exist in iOS 27 (valid e.g. {", ".join(x for x in sorted(CK_KEYS) if "email" in x or "phone" in x)})')
            if 'attachmentsByRange' in v:
                s = v.get('string', '')
                u16 = s.encode('utf-16-le')
                for rk, att in v['attachmentsByRange'].items():
                    m = re.fullmatch(r'\{(\d+), (\d+)\}', rk)
                    if not m: r.err(w, f'{path}: bad range key {rk!r}'); continue
                    loc, ln = int(m[1]), int(m[2])
                    if u16[loc*2:(loc+ln)*2].decode('utf-16-le', 'replace') != FFFC: r.err(w, f'{path}: range {rk} does not point at a U+FFFC placeholder (UTF-16 offset)')
                if s.count(FFFC) != len(v['attachmentsByRange']): r.err(w, f'{path}: {s.count(FFFC)} placeholders but {len(v["attachmentsByRange"])} attachments')
            if v.get('Type') == 'ActionOutput':
                ou = v.get('OutputUUID')
                if ou not in uuids: r.err(w, f'{path}: refers to OutputUUID {ou} that no EARLIER action defines')
        walk(params, check)
    for g, lst in groups.items():
        modes = [m for _, m, _ in lst]
        if modes[0] != 0 or modes[-1] != 2 or any(m not in (0, 1, 2) for m in modes):
            r.err(f'group {g}', f'control-flow block not opened/closed properly: modes {modes}')
        if len({i for _, _, i in lst}) != 1: r.err(f'group {g}', 'control-flow block mixes action types')
    # nesting check
    stack = []
    for n, a in enumerate(p.get('WFWorkflowActions', [])):
        pr = a.get('WFWorkflowActionParameters', {})
        if 'WFControlFlowMode' not in pr: continue
        m, g = pr['WFControlFlowMode'], pr.get('GroupingIdentifier')
        if m == 0: stack.append(g)
        elif not stack or stack[-1] != g: r.err(f'[{n}]', 'control-flow blocks overlap instead of nesting')
        elif m == 2: stack.pop()
    if stack: r.err('end', f'{len(stack)} control-flow block(s) never closed')

# ---------------------------------------------------------------- simulation
class Sim:
    def __init__(s, p, mocks, live_get, shortcut_input):
        s.p, s.m, s.live = p, mocks, live_get
        s.out, s.vars, s.log = {}, {}, []
        s.side = {'emails': [], 'reminders': [], 'notifications': [], 'http': [], 'opened_urls': [], 'shown': []}
        s.input = shortcut_input
    def resolve_att(s, att, ctx):
        t = att.get('Type')
        if t == 'ActionOutput':
            if att.get('OutputUUID') not in s.out: raise RuntimeError(f'variable "{att.get("OutputName")}" used before its action ran (crash/empty on iPhone)')
            return s.out[att['OutputUUID']]
        if t == 'Variable':
            name = att.get('VariableName')
            if name == 'Repeat Item': return ctx.get('repeat_item')
            if name == 'Repeat Index': return ctx.get('repeat_index')
            return s.vars.get(name)
        if t == 'ExtensionInput': return s.input
        if t == 'CurrentDate': return datetime.datetime.now().isoformat(timespec='minutes')
        if t == 'Clipboard': return s.m.get('clipboard', '')
        if t == 'Ask': return s.m.get('ask', 'mock answer')
        return f'<{t}>'
    def val(s, v, ctx):
        if isinstance(v, dict):
            st = v.get('WFSerializationType')
            if st == 'WFTextTokenString':
                txt, atts = v['Value'].get('string', ''), v['Value'].get('attachmentsByRange', {})
                u = list(txt.encode('utf-16-le')); res = txt
                parts = []; last = 0; u16 = txt.encode('utf-16-le')
                for rk in sorted(atts, key=lambda k: int(k[1:].split(',')[0])):
                    loc = int(rk[1:].split(',')[0])
                    parts.append(u16[last*2:loc*2].decode('utf-16-le')); x = s.resolve_att(atts[rk], ctx)
                    parts.append(s.text(x)); last = loc + 1
                parts.append(u16[last*2:].decode('utf-16-le'))
                return ''.join(parts)
            if st == 'WFTextTokenAttachment': return s.resolve_att(v['Value'], ctx)
            if st == 'WFContactFieldValue':
                out = []
                for e in v['Value'].get('WFContactFieldValues', []):
                    se = e.get('SerializedEntry', {})
                    if 'link.contentkit.emailaddress' in se: out.append(se['link.contentkit.emailaddress'])
                    elif se: raise RuntimeError(f'contact entry with unknown keys {list(se)}: iOS cannot build a WFEmailAddress from it ("WFContactFieldEntry could not init WFEmailAddress")')
                    elif 'WFContactData' in e: out.append(re.findall(r'EMAIL[^:]*:([^\r\n]+)', str(e['WFContactData'])) or ['<contact>'])
                return out
            if st in ('WFStringSubstitutableState', 'WFNumberSubstitutableState'): return s.val(v['Value'], ctx)
            if st == 'WFDictionaryFieldValue':
                return {s.text(s.val(it.get('WFKey'), ctx)): s.val(it.get('WFValue'), ctx) for it in v['Value'].get('WFDictionaryFieldValueItems', [])}
            if 'Type' in v and 'Variable' in v: return s.val(v['Variable'], ctx)
            return v
        return v
    def text(s, x):
        if isinstance(x, list): return '\n'.join(s.text(i) for i in x)
        if isinstance(x, dict) and 'type' in x and 'value' in x: return f'{x["type"]}: {x["value"]} ({x.get("start")} → {x.get("end")})'
        return '' if x is None else str(x)
    def run(s):
        acts = s.p['WFWorkflowActions']
        s.exec_range(acts, 0, len(acts), {})
        return s
    def find_block(s, acts, i):
        g = acts[i]['WFWorkflowActionParameters'].get('GroupingIdentifier'); mids = []
        for j in range(i + 1, len(acts)):
            pr = acts[j]['WFWorkflowActionParameters']
            if pr.get('GroupingIdentifier') == g:
                if pr.get('WFControlFlowMode') == 1: mids.append(j)
                if pr.get('WFControlFlowMode') == 2: return mids, j
        raise RuntimeError('unterminated block')
    def exec_range(s, acts, i, end, ctx):
        while i < end:
            a = acts[i]; ident = a['WFWorkflowActionIdentifier']; pr = a.get('WFWorkflowActionParameters', {})
            short = ident.replace('is.workflow.actions.', '')
            if pr.get('WFControlFlowMode') == 0 and short in ('repeat.each', 'repeat.count', 'conditional', 'choosefrommenu'):
                mids, j = s.find_block(acts, i)
                if short == 'repeat.each':
                    items = s.val(pr.get('WFInput'), ctx); items = items if isinstance(items, list) else [items]
                    s.log.append(f'[{i}] Repeat with Each over {len(items)} item(s)'); res = []
                    for k, it in enumerate(items):
                        c = dict(ctx, repeat_item=it, repeat_index=k + 1); s.exec_range(acts, i + 1, j, c); res.append(s.last)
                    s.out[pr.get('UUID')] = res; s.out[acts[j]['WFWorkflowActionParameters'].get('UUID')] = res
                elif short == 'repeat.count':
                    n = int(s.val(pr.get('WFRepeatCount', 1), ctx) or 1)
                    for k in range(n): s.exec_range(acts, i + 1, j, dict(ctx, repeat_index=k + 1))
                elif short == 'conditional':
                    x = s.val(pr.get('WFInput'), ctx); cond = pr.get('WFCondition', 100); ref = s.val(pr.get('WFConditionalActionString'), ctx)
                    tx = s.text(x)
                    truth = {100: bool(tx.strip()), 101: not tx.strip(), 4: tx == s.text(ref), 5: tx != s.text(ref), 99: s.text(ref) in tx,
                             999: bool(tx.strip())}.get(cond, bool(tx))
                    s.log.append(f'[{i}] If (cond {cond}) on {tx[:40]!r} → {truth}')
                    other = mids[0] if mids else j
                    s.last = None
                    if truth: s.exec_range(acts, i + 1, other, ctx)
                    elif mids: s.exec_range(acts, mids[0] + 1, j, ctx)
                    s.out[acts[j]['WFWorkflowActionParameters'].get('UUID')] = s.last
                else:
                    s.log.append(f'[{i}] Choose from Menu: taking first branch (mock)')
                    if mids: s.exec_range(acts, mids[0] + 1, mids[1] if len(mids) > 1 else j, ctx)
                i = j + 1; continue
            if pr.get('WFControlFlowMode') in (1, 2): i += 1; continue
            res = s.step(i, short, ident, pr, ctx)
            s.last = res
            if 'UUID' in pr: s.out[pr['UUID']] = res
            i += 1
    def step(s, i, short, ident, pr, ctx):
        L = s.log.append; v = lambda k, d=None: s.val(pr.get(k, d), ctx)
        if short == 'comment': return None
        if short == 'gettext': r = v('WFTextActionText', ''); L(f'[{i}] Text = {s.text(r)[:60]!r}'); return r
        if short == 'setvariable': s.vars[pr['WFVariableName']] = v('WFInput'); L(f'[{i}] Set variable {pr["WFVariableName"]} = {s.text(s.vars[pr["WFVariableName"]])[:60]!r}'); return s.vars[pr['WFVariableName']]
        if short == 'appendvariable': s.vars.setdefault(pr['WFVariableName'], []); s.vars[pr['WFVariableName']] = (s.vars[pr['WFVariableName']] if isinstance(s.vars[pr['WFVariableName']], list) else [s.vars[pr['WFVariableName']]]) + [v('WFInput')]; return s.vars[pr['WFVariableName']]
        if short == 'getvariable': return v('WFVariable')
        if short == 'filter.health.quantity':
            tmpl = pr.get('WFContentItemFilter', {}).get('Value', {}).get('WFActionParameterFilterTemplates', [])
            typ = next((t['Values']['Enumeration']['Value'] for t in tmpl if t.get('Property') == 'Type' and 'Enumeration' in t.get('Values', {})), None)
            if typ is None: raise RuntimeError('Find Health Samples has no Type filter')
            samples = s.m.get('health', {}).get(typ)
            if samples is None: L(f'[{i}] Find Health Samples type={typ!r}: NO mock data for this type (on iPhone: empty result or unknown type)'); return []
            L(f'[{i}] Find Health Samples type={typ!r} → {len(samples)} sample(s) (mock)')
            return [dict(x, type=typ) for x in samples]
        if short == 'properties.health.quantity':
            x = v('WFInput'); prop = pr.get('WFContentItemPropertyName'); return (x or {}).get({'Start Date': 'start', 'End Date': 'end', 'Value': 'value'}.get(prop, prop.lower()))
        if short == 'sendemail':
            to = v('WFSendEmailActionToRecipients'); to = to if isinstance(to, list) else [s.text(to)]
            mail = {'to': to, 'subject': s.text(v('WFSendEmailActionSubject', '')), 'body': s.text(v('WFSendEmailActionInputAttachments', '')),
                    'compose_sheet': pr.get('WFSendEmailActionShowComposeSheet', True)}
            if not to or not any(to): raise RuntimeError('Send Email has no recipient')
            s.side['emails'].append(mail); L(f'[{i}] Send Email (mock) to {to} subject {mail["subject"]!r}, {len(mail["body"])} chars, compose sheet={mail["compose_sheet"]}'); return None
        if short == 'addnewreminder':
            t = s.text(v('WFCalendarItemTitle', '')); s.side['reminders'].append(t); L(f'[{i}] Add Reminder (mock): {t[:60]!r}'); return t
        if short == 'notification':
            t = s.text(v('WFNotificationActionBody', '')); s.side['notifications'].append(t); L(f'[{i}] Notification (mock): {t[:60]!r}'); return None
        if short in ('showresult', 'alert'):
            t = s.text(v('Text', v('WFAlertActionMessage', ''))); s.side['shown'].append(t); L(f'[{i}] Show (mock): {t[:60]!r}'); return None
        if short == 'getbatterylevel': b = s.m.get('battery', 87); L(f'[{i}] Battery = {b} (mock)'); return b
        if short in ('url',): return v('WFURLActionURL')
        if short in ('openurl',): u = s.text(v('WFInput')); s.side['opened_urls'].append(u); L(f'[{i}] Open URL (mock): {u}'); return None
        if short == 'downloadurl':
            u = s.text(v('WFURL')); method = pr.get('WFHTTPMethod', 'GET')
            req = {'method': method, 'url': u}
            if pr.get('WFJSONValues'): req['json'] = {k: s.text(x) for k, x in v('WFJSONValues').items()}
            s.side['http'].append(req)
            for pat, body in s.m.get('http', {}).items():
                if pat in u: L(f'[{i}] Get Contents of URL (mock match {pat!r}) {method} {u[:80]}'); return body
            if s.live and method == 'GET':
                body = urllib.request.urlopen(u, timeout=15).read().decode('utf-8', 'replace'); L(f'[{i}] Get Contents of URL (LIVE GET) {u[:80]} → {len(body)} chars'); return body
            L(f'[{i}] Get Contents of URL (mock, no rule) {method} {u[:80]} → ""'); return ''
        if short == 'text.split':
            x = s.text(v('text', v('WFInput'))); sep = pr.get('WFTextSeparator', 'New Lines')
            sep = {'New Lines': '\n', 'Spaces': ' ', 'Every Character': ''}.get(sep, pr.get('WFTextCustomSeparator', '\n'))
            parts = list(x) if sep == '' else [p for p in x.split(sep)]; L(f'[{i}] Split Text → {len(parts)} part(s)'); return parts
        if short == 'text.combine':
            x = v('text', v('WFInput')); x = x if isinstance(x, list) else [x]; return {'New Lines': '\n', 'Spaces': ' '}.get(pr.get('WFTextSeparator', 'New Lines'), pr.get('WFTextCustomSeparator', '')).join(s.text(i) for i in x)
        if short == 'getitemfromlist':
            x = v('WFInput'); x = x if isinstance(x, list) else [x]; spec = pr.get('WFItemSpecifier', 'First Item')
            return (x[0] if spec == 'First Item' else x[-1] if spec == 'Last Item' else x[int(pr.get('WFItemIndex', 1)) - 1]) if x else None
        if short == 'count': x = v('Input', v('WFInput')); return len(x) if isinstance(x, list) else (1 if x else 0)
        if short == 'ask': a = s.m.get('ask', 'mock answer'); L(f'[{i}] Ask for Input → {a!r} (mock)'); return a
        if short == 'list': return [s.text(s.val(x, ctx)) for x in pr.get('WFItems', [])]
        if short == 'number': return v('WFNumberActionNumber')
        if short == 'date': return datetime.datetime.now().isoformat()
        L(f'[{i}] {ident}: NOT SIMULATED (passed through as empty output)'); s.unsupported = getattr(s, 'unsupported', []) + [ident]; return None

DEFAULT_MOCKS = {
    'health': {'Sleep': [
        {'value': 'Asleep (Core)', 'start': '2026-10-20T23:40', 'end': '2026-10-21T02:10'},
        {'value': 'Asleep (Deep)', 'start': '2026-10-21T02:10', 'end': '2026-10-21T03:00'},
        {'value': 'Asleep (REM)', 'start': '2026-10-21T03:00', 'end': '2026-10-21T05:45'}],
        'Steps': [{'value': 8421, 'start': '2026-10-20T00:00', 'end': '2026-10-21T00:00'}]},
    'battery': 100, 'http': {'ntfy.sh/': 'REMIND|Buy milk\nREMIND|Call tax office'}, 'ask': 'mock answer', 'clipboard': ''}

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['validate', 'run', 'dump']); ap.add_argument('files', nargs='+')
    ap.add_argument('--mocks'); ap.add_argument('--live-get', action='store_true'); ap.add_argument('--input', default=None); ap.add_argument('--json', action='store_true')
    a = ap.parse_args(); rc = 0
    mocks = json.load(open(a.mocks)) if a.mocks else DEFAULT_MOCKS
    for f in a.files:
        try: p, info = load(f)
        except Exception as e: print(f'== {f}\n  ERROR cannot decode: {e}'); rc = 1; continue
        if a.cmd == 'dump': print(json.dumps(p, indent=1, ensure_ascii=False, default=str)); continue
        if a.cmd == 'validate':
            r = Report(); validate(p, r)
            print(f'== {f}  ({"signed" if info["signed"] else "unsigned"}, {len(p.get("WFWorkflowActions", []))} actions, client {p.get("WFWorkflowClientVersion")})')
            for lvl, w, m in r.items: print(f'  {lvl:5} {w}: {m}')
            print('  RESULT:', 'PASS' if r.ok() else 'FAIL', f'({sum(l=="ERROR" for l,_,_ in r.items)} errors, {sum(l=="WARN" for l,_,_ in r.items)} warnings)')
            rc |= 0 if r.ok() else 1
        if a.cmd == 'run':
            print(f'== RUN {f}')
            r = Report(); validate(p, r)
            if not r.ok(): print('  (validator found errors; simulating anyway)')
            sim = Sim(p, mocks, a.live_get, a.input)
            try: sim.run(); status = 'completed'
            except Exception as e: status = f'STOPPED: {e}'; rc = 1
            for l in sim.log: print('  ' + l)
            print('  side effects:', json.dumps({k: v for k, v in sim.side.items() if v}, ensure_ascii=False, indent=1).replace('\n', '\n  '))
            print('  status:', status)
    sys.exit(rc)

if __name__ == '__main__': main()

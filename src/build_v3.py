"""Health Sync v3: proven Find Health Samples block -> one readable line per sample -> JSON POST to ntfy.
Every action shape mirrors a real export:
  filter.health.quantity  copied from 4ee674e4 (Read Last Night's Sleep)
  repeat.each / properties.health.quantity (Start Date, Value, Duration) from be5be7df (Sleep Summary)
  gettext token string with ActionOutput attachments from 4ee674e4
  text.combine on Repeat Results from 9b08f3da (default separator = New Lines, as in 51cc4e26)
  downloadurl POST + WFJSONValues from 7ada1993 (brrr Example)"""
import os, sys, plistlib, copy
sys.path.insert(0, '/workspace/.venv-sk/lib/python3.12/site-packages')
from shortcutkit import Shortcut, ref, text, repeat_item
TOPIC = os.environ.get('NTFY_TOPIC', 'YOUR-NTFY-TOPIC') + '-h'

refp = plistlib.load(open('/workspace/iphone-shortcuts/ref/4ee674e49d18438ba426dc0b93598109.shortcut', 'rb'))
HEALTH = next(copy.deepcopy(a['WFWorkflowActionParameters']) for a in refp['WFWorkflowActions']
              if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.filter.health.quantity')
HEALTH.pop('UUID')

def kv(key, value):
    return {'WFItemType': 0, 'WFKey': text(key), 'WFValue': value}

s = Shortcut('Health Sync v3', color='Blue', glyph=59754)
h = s.action('is.workflow.actions.filter.health.quantity', **HEALTH)
g = s.repeat_each(ref(h, 'Health Samples'))
d = {}
for prop in ['Start Date', 'End Date', 'Value', 'Duration']:
    d[prop] = s.action('is.workflow.actions.properties.health.quantity', WFInput=repeat_item(), WFContentItemPropertyName=prop)
line = s.action('is.workflow.actions.gettext', WFTextActionText=text(
    ref(d['Start Date'], 'Start Date'), ' - ', ref(d['End Date'], 'End Date'), ' ', ref(d['Value'], 'Value'), ' ', ref(d['Duration'], 'Duration')))
rr = s.end_repeat_each(g)
comb = s.action('is.workflow.actions.text.combine', text=ref(rr, 'Repeat Results'))
s.action('is.workflow.actions.downloadurl', WFURL='https://ntfy.sh', WFHTTPMethod='POST',
         WFJSONValues={'Value': {'WFDictionaryFieldValueItems': [
             kv('topic', text(TOPIC)),
             kv('title', text('health-sync')),
             kv('message', text('Sleep samples (last 1 day):\n', ref(comb, 'Combined Text')))]},
           'WFSerializationType': 'WFDictionaryFieldValue'})
p = s.to_plist()
for a in p['WFWorkflowActions']:
    prm = a['WFWorkflowActionParameters']
    if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.text.combine':
        # real exports store this input as a bare attachment; shortcutkit wraps text-kind params
        prm['text'] = {'Value': prm['text']['Value']['attachmentsByRange']['{0, 1}'], 'WFSerializationType': 'WFTextTokenAttachment'}
    if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.downloadurl':
        prm['WFURL'] = 'https://ntfy.sh'   # plain string exactly like 7ada1993
open('/workspace/iphone-shortcuts/v2/Health Sync v3.plist', 'wb').write(plistlib.dumps(p, fmt=plistlib.FMT_XML))
print('built', len(p['WFWorkflowActions']), 'actions')

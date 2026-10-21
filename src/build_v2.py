"""Build v2 shortcuts with shortcutkit (validates keys/kinds at build time). Every action's parameter
shape mirrors a real Apple-exported shortcut (see ../ref). Writes XML plists to v2/; signing is separate."""
import os, sys, plistlib, copy
sys.path.insert(0, '/workspace/.venv-sk/lib/python3.12/site-packages')
from shortcutkit import Shortcut, ref, text, variable, repeat_item, subject
TOPIC = os.environ.get('NTFY_TOPIC', 'YOUR-NTFY-TOPIC')
OUT = '/workspace/iphone-shortcuts/v2'
EMAIL = 'you@example.com'

# Find Health Samples parameters copied from real export 4ee674e4 ("Read Last Night's Sleep", client 3607.0.2):
# Type is Sleep, Start Date is in the last 1 day, sort Start Date Oldest First. Only the UUID is new.
ref_health = plistlib.load(open('/workspace/iphone-shortcuts/ref/4ee674e49d18438ba426dc0b93598109.shortcut', 'rb'))
HEALTH = next(copy.deepcopy(a['WFWorkflowActionParameters']) for a in ref_health['WFWorkflowActions']
              if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.filter.health.quantity')
HEALTH.pop('UUID')

def email_block(s, subject_text, body):
    # Recipient as a Text variable: the exact shape of real export d62e7adb ("Scan to Email").
    t = s.action('is.workflow.actions.gettext', WFTextActionText=EMAIL)
    s.action('is.workflow.actions.setvariable', WFVariableName='GrokEmail', WFInput=ref(t, 'Text'))
    s.action('is.workflow.actions.sendemail',
             WFSendEmailActionToRecipients=variable('GrokEmail'),
             WFSendEmailActionSubject=text(subject_text),
             WFSendEmailActionInputAttachments=body,
             WFSendEmailActionShowComposeSheet=False)

def save(s, name):
    p = s.to_plist()
    for a in p['WFWorkflowActions']:
        if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.text.split':
            # Real export 51cc4e26 stores Split Text's input as a bare attachment (Show-text UI flag omitted);
            # shortcutkit wraps it as a token string, so restore Apple's shape.
            prm = a['WFWorkflowActionParameters']
            prm['text'] = {'Value': prm['text']['Value']['attachmentsByRange']['{0, 1}'], 'WFSerializationType': 'WFTextTokenAttachment'}
    open(f'{OUT}/{name}.plist', 'wb').write(plistlib.dumps(p, fmt=plistlib.FMT_XML))
    print('built', name, len(p['WFWorkflowActions']), 'actions')

# Health Test
s = Shortcut('Health Test', color='Blue', glyph=59754)
email_block(s, '[HEALTH SYNC] test', text('[HEALTH SYNC] test'))
save(s, 'Health Test')

# Health Sync v2
s = Shortcut('Health Sync v2', color='Blue', glyph=59754)
h = s.action('is.workflow.actions.filter.health.quantity', **HEALTH)
email_block(s, '[HEALTH SYNC]', text(ref(h, 'Health Samples')))
save(s, 'Health Sync v2')

# Grok Inbox v2
s = Shortcut('Grok Inbox v2', color='Green', glyph=59754)
dl = s.action('is.workflow.actions.downloadurl', WFURL=text(f'https://ntfy.sh/{TOPIC}-q/raw?poll=1&since=60m'))
sp = s.action('is.workflow.actions.text.split', text=ref(dl, 'Contents of URL'))   # default separator = New Lines
g = s.repeat_each(ref(sp, 'Split Text'))
c = s.if_(repeat_item(), 'has_any_value')
s.action('is.workflow.actions.addnewreminder', WFCalendarItemTitle=text(repeat_item()))   # shape of real export 0a138836
s.end_if(c)
s.end_repeat_each(g)
b = s.action('is.workflow.actions.getbatterylevel')
s.action('is.workflow.actions.downloadurl', WFURL=text(f'https://ntfy.sh/{TOPIC}-r/publish?message=inbox-ok%20battery%3D', ref(b, 'Battery Level')))
save(s, 'Grok Inbox v2')

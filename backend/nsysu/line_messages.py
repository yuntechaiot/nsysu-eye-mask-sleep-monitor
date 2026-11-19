"""Use the exact cloud copy in isolated local LINE previews; no sending here."""
import json

from .config import ROOT

COPY = json.loads((ROOT / 'supabase/functions/nsysu-line/messages.json').read_text(encoding='utf-8'))


def line_text(name, **values):
    return COPY[name].format(**values)


def reminder_text(member, day, slot):
    return line_text('morning' if slot == '09:00' else 'follow_up') + '\n' + line_text(
        'diary_context', member=member, day=day.replace('-', '/'))

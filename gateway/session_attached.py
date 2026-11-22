"""What a session is about: ``attached = {kind: task|project|decision, id}``, set once by its client.

A client names it on ``session.create`` or on a ``prompt.submit`` (the first one that carries it wins;
a later one never moves the session). Stored as one core-owned ``state_meta`` key per session, the
same per-session bookkeeping goals and API settings use, so routing state (``origin_json``) and the
history authorization that reads it are untouched; ``retire_sessions`` drops the key with the row.
"""
from __future__ import annotations

import json

from persistence.core.errors import AuthorityRefusal

KINDS = ('task', 'project', 'decision')
ID_MAX = 128
PREFIX = 'session.attached.v1.'


def parse(value):
    """The validated ``{kind, id}``, or ``None`` when *value* is ``None``; anything else is refused."""
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'kind', 'id'} or value['kind'] not in KINDS
            or not isinstance(value['id'], str) or not value['id'].strip() or len(value['id']) > ID_MAX):
        raise AuthorityRefusal('invalid_params', field='attached',
                               detail=f'kind one of {"/".join(KINDS)}, id 1-{ID_MAX} chars')
    return {'kind': value['kind'], 'id': value['id'].strip()}


def set_if_unset(store, session_id, attached):
    """First writer wins; returns what the session is attached to afterwards."""
    key = PREFIX + session_id
    saved = store.state_meta.get(key)
    if saved is None:
        store.state_meta.set(key, json.dumps(attached, separators=(',', ':')))
        return attached
    return json.loads(saved)


def read(store, session_id):
    saved = store.state_meta.get(PREFIX + session_id)
    return json.loads(saved) if saved else None


def sessions_attached_to(store, kind, attached_id):
    """Session ids attached to ``kind``/``attached_id``, in the order they were attached."""
    wanted = {'kind': kind, 'id': attached_id}
    out = []
    for entry in store.state_meta.list_prefix(PREFIX):
        try:
            if json.loads(entry.value) == wanted:
                out.append(entry.key[len(PREFIX):])
        except ValueError:
            continue
    return out

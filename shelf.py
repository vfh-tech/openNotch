import json
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

MAX_TEXT = 4000
VERSION = 1


@dataclass
class ShelfItem:
    kind: str
    value: str
    label: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def path(self):
        if self.kind != 'file':
            return None
        parsed = urlsplit(self.value)
        if parsed.scheme != 'file':
            return None
        return Path(unquote(parsed.path))

    @property
    def exists(self):
        if self.kind == 'text':
            return True
        path = self.path
        return bool(path and path.exists())

    def to_dict(self):
        return {'id': self.id, 'kind': self.kind, 'value': self.value, 'label': self.label}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return None
        kind, value, label = data.get('kind'), data.get('value'), data.get('label')
        if kind not in ('file', 'text', 'link') or not isinstance(value, str) or not value:
            return None
        return cls(kind, value, str(label or value)[:120], data.get('id') or uuid.uuid4().hex)


def parse_drop(uri_text, files, limit=8):
    items = []
    for uri in (uri_text or '').splitlines():
        uri = uri.strip()
        if not uri or uri.startswith('#'):
            continue
        if uri.startswith('file://'):
            items.append(ShelfItem('file', uri, Path(unquote(urlsplit(uri).path)).name or uri))
        elif uri.startswith(('http://', 'https://')):
            items.append(ShelfItem('link', uri, urlstrip(uri)))
        if len(items) >= limit:
            return items
    for name in files or ():
        path = Path(name)
        if path.exists():
            items.append(ShelfItem('file', path.as_uri(), path.name))
        if len(items) >= limit:
            return items
    if not items and uri_text and len(uri_text) <= MAX_TEXT:
        text = uri_text.strip()
        if text:
            items.append(ShelfItem('text', text, text[:60]))
    return items[:limit]


def urlstrip(uri):
    parsed = urlsplit(uri)
    return (parsed.netloc + parsed.path).strip('/')[:120] or uri[:120]


class ShelfStore:
    def __init__(self, path, limit=8):
        self.path = Path(path)
        self.limit = limit
        self.items = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(data, dict) or data.get('version') != VERSION:
            return []
        loaded = [ShelfItem.from_dict(entry) for entry in data.get('items', [])]
        return [item for item in loaded if item is not None][-self.limit:]

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({'version': VERSION, 'items': [i.to_dict() for i in self.items]}, indent=2)
        handle = tempfile.NamedTemporaryFile('w', dir=self.path.parent, delete=False,
                                             prefix='.shelf-', suffix='.json')
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            os.replace(handle.name, self.path)
        except OSError:
            Path(handle.name).unlink(missing_ok=True)

    def add(self, item):
        if any(i.value == item.value and i.kind == item.kind for i in self.items):
            return False
        self.items.append(item)
        del self.items[:-self.limit]
        self._save()
        return True

    def add_all(self, new_items):
        added = sum(1 for item in new_items if self.add(item))
        return added

    def remove(self, item_id):
        before = len(self.items)
        self.items = [i for i in self.items if i.id != item_id]
        if len(self.items) != before:
            self._save()
            return True
        return False
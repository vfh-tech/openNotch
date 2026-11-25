import json
import os
import tempfile
from pathlib import Path

DEFAULTS = {
    'width': 368,
    'hover_delay_ms': 100,
    'agenda_limit': 4,
    'show_agenda': True,
    'show_media': True,
    'scroll_navigation': True,
}

RANGES = {
    'width': (280, 640),
    'hover_delay_ms': (0, 800),
    'agenda_limit': (0, 8),
}

VERSION = 1


def clamp(key, value):
    if key in DEFAULTS and isinstance(DEFAULTS[key], bool):
        return value if isinstance(value, bool) else DEFAULTS[key]
    low, high = RANGES.get(key, (None, None))
    if low is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULTS[key]
    return max(low, min(high, value))


class NotchSettings:
    def __init__(self, path):
        self.path = Path(path)
        self.values = dict(DEFAULTS)
        self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get('version') != VERSION:
            return
        stored = data.get('values')
        if not isinstance(stored, dict):
            return
        for key, value in stored.items():
            normalized = clamp(key, value)
            if normalized is not None:
                self.values[key] = normalized

    def set(self, key, value):
        normalized = clamp(key, value)
        if normalized is None:
            return None
        self.values[key] = normalized
        self._save()
        return normalized

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({'version': VERSION,
                              'values': {k: v for k, v in self.values.items() if k in DEFAULTS}},
                             indent=2)
        handle = tempfile.NamedTemporaryFile('w', dir=self.path.parent, delete=False,
                                            prefix='.notch-', suffix='.json')
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            os.replace(handle.name, self.path)
        except OSError:
            Path(handle.name).unlink(missing_ok=True)

    def __getitem__(self, key):
        return self.values[key]
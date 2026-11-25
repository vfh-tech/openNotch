from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Kind(Enum):
    EVENT = 'VEVENT'
    TASK = 'VTODO'


def classify(component):
    try:
        return Kind(component)
    except ValueError:
        return None


@dataclass(frozen=True)
class AgendaEntry:
    title: str
    kind: Kind
    start: datetime
    all_day: bool = False
    done: bool = False
    source: str = ''

    @property
    def time_text(self):
        if self.all_day:
            return 'Sepanjang hari'
        return self.start.strftime('%H:%M')

    @property
    def overdue(self):
        return self.kind is Kind.TASK and not self.done and self.start < datetime.now()


class AgendaModel:
    def __init__(self, limit=4):
        self.limit = limit
        self.entries = []
        self.total = 0

    def replace(self, entries):
        ordered = sorted(entries, key=lambda e: (e.kind is not Kind.EVENT, e.start, e.title))
        self.total = len(ordered)
        self.entries = ordered[:self.limit]

    @property
    def summary(self):
        if not self.total:
            return 'Tidak ada agenda hari ini'
        if self.total > len(self.entries):
            return f'{len(self.entries)} dari {self.total} agenda'
        return f'{self.total} agenda'

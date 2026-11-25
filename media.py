from dataclasses import dataclass
from enum import Enum, auto


class Playback(Enum):
    STOPPED = auto()
    PAUSED = auto()
    PLAYING = auto()


@dataclass(frozen=True)
class PlayerSnapshot:
    name: str
    playback: Playback
    track_id: str = ''
    title: str = ''
    artist: str = ''
    art_url: str | None = None
    length_us: int | None = None
    can_control: bool = True
    can_play: bool = True
    can_pause: bool = True
    can_next: bool = False
    can_previous: bool = False
    can_seek: bool = False


def format_clock(microseconds):
    if microseconds is None:
        return ''
    total = max(0, microseconds) // 1_000_000
    return f'{total // 60}:{total % 60:02d}'


class MediaModel:
    def __init__(self):
        self.pinned = None
        self.visible = None
        self.last = (None, '')

    @property
    def selected(self):
        return self.pinned or self.visible

    def prefer(self, name):
        self.pinned = name

    def vanish(self, name):
        if self.pinned == name:
            self.pinned = None
        if self.visible == name:
            self.visible = None

    def choose(self, players):
        chosen = next((p for p in players if p.name == self.pinned), None)
        if chosen is None:
            chosen = next((p for p in players if p.playback is Playback.PLAYING),
                          players[0] if players else None)
            if self.pinned is None and chosen is not None:
                self.pinned = chosen.name
        self.visible = chosen.name if chosen else None
        return chosen

    def track_changed(self, snapshot):
        return snapshot is not None and (snapshot.name, snapshot.track_id) != self.last

    def accept(self, snapshot):
        self.last = (snapshot.name, snapshot.track_id) if snapshot else (None, '')

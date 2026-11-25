from dataclasses import dataclass
from enum import Enum, auto


class Page(Enum):
    UNAVAILABLE = auto()
    CLOSED = auto()
    TRAY = auto()
    BANNER = auto()


@dataclass(frozen=True)
class Banner:
    app: str
    title: str
    body: str


@dataclass
class NotchState:
    output: bool = False
    hover: bool = False
    menu: bool = False
    drag: bool = False
    manual: bool = False
    banner: Banner | None = None
    outgoing: Banner | None = None
    queued: Banner | None = None

    @property
    def page(self):
        if not self.output:
            return Page.UNAVAILABLE
        if self.banner is not None:
            return Page.BANNER
        if self.hover or self.menu or self.drag or self.manual:
            return Page.TRAY
        return Page.CLOSED

    def set_output(self, available):
        self.output = available
        if not available:
            self.hover = self.menu = self.drag = self.manual = False
            self.outgoing = None

    def show(self, banner):
        self.banner = banner
        self.outgoing = None

    def dismiss(self, *, animate=False):
        banner, self.banner = self.banner, None
        self.outgoing = banner if animate and self.page is Page.CLOSED else None

    def take_queued(self):
        if not self.output or self.banner is not None:
            return None
        banner, self.queued = self.queued, None
        return banner

import math
import time

from gi.repository import GLib, Gtk


class FocusTimer(Gtk.Box):
    def __init__(self, changed, finished, width, duration=25 * 60,
                 clock=lambda: time.clock_gettime(time.CLOCK_BOOTTIME)):
        super().__init__(spacing=6)
        self.set_size_request(width, 36)
        self.duration = duration
        self.clock = clock
        self.changed = changed
        self.finished = finished
        self.deadline = self.paused = None
        self.source = 0
        self.label = Gtk.Label(xalign=0)
        self.toggle = Gtk.Button()
        self.toggle.connect('clicked', self.toggle_timer)
        self.reset = Gtk.Button(label='Reset')
        self.reset.connect('clicked', self.reset_timer)
        self.pack_start(self.label, True, True, 0)
        self.pack_start(self.toggle, False, False, 0)
        self.pack_start(self.reset, False, False, 0)
        self.update()

    @property
    def running(self):
        return self.deadline is not None

    @property
    def countdown(self):
        if self.running:
            return max(0, self.deadline - self.clock())
        return self.paused

    @staticmethod
    def format_time(seconds):
        minute, second = divmod(math.ceil(seconds), 60)
        return f'{minute:02d}:{second:02d}'

    def update(self):
        remaining = self.countdown
        self.label.set_text(f'Fokus · {self.format_time(self.duration if remaining is None else remaining)}')
        self.toggle.set_label('Jeda' if self.running else 'Mulai' if remaining is None else 'Lanjut')
        self.reset.set_sensitive(remaining is not None)

    def toggle_timer(self, _button):
        if self.running:
            remaining = self.countdown
            self.stop_tick()
            self.deadline = None
            if remaining <= 0:
                self.finished()
            else:
                self.paused = remaining
        else:
            remaining = self.duration if self.paused is None else self.paused
            self.deadline = self.clock() + remaining
            self.paused = None
            self.source = GLib.timeout_add(250, self.tick)
        self.update()
        self.changed()

    def stop_tick(self):
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0

    def reset_timer(self, _button):
        self.stop_tick()
        self.deadline = self.paused = None
        self.update()
        self.changed()

    def tick(self):
        if self.countdown <= 0:
            self.source = 0
            self.deadline = None
            self.update()
            self.changed()
            self.finished()
            return GLib.SOURCE_REMOVE
        self.update()
        self.changed()
        return GLib.SOURCE_CONTINUE

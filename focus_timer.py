import math
import time

from gi.repository import GLib, Gtk

MIN_MINUTES = 1
MAX_MINUTES = 180



BLINK_MS = 620
GREEN = (0.20, 0.94, 0.42)
def dot_pixbuf(size=10):
    from gi.repository import GdkPixbuf
    import cairo
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx = cairo.Context(surface)
    ctx.set_source_rgba(*GREEN, 1.0)
    ctx.arc(size / 2, size / 2, size / 2 - 1, 0, math.tau)
    ctx.fill()
    surface.flush()
    stride = surface.get_stride()
    raw = bytes(surface.get_data())
    out = bytearray()
    for y in range(size):
        row = raw[y * stride:y * stride + size * 4]
        for i in range(0, size * 4, 4):
            b, g, r, a = row[i], row[i + 1], row[i + 2], row[i + 3]
            out += bytes((r, g, b, a))
    return GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(out)),
                                           GdkPixbuf.Colorspace.RGB, True, 8,
                                           size, size, size * 4)


def clamp_minutes(minutes):
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        return 25
    return max(MIN_MINUTES, min(MAX_MINUTES, minutes))


class FocusTimer(Gtk.Box):
    def __init__(self, changed, finished, width, duration=25 * 60,
                 clock=lambda: time.clock_gettime(time.CLOCK_BOOTTIME), minutes=None):
        super().__init__(spacing=6)
        self.set_size_request(width, 36)
        self.duration = duration
        self.clock = clock
        self.changed = changed
        self.finished = finished
        self.deadline = self.paused = None
        self.source = 0

        self.label = Gtk.Label(xalign=0)
        self.led = Gtk.Image.new_from_pixbuf(dot_pixbuf())
        self.led.set_tooltip_text('Sesi fokus berjalan')
        self.led.get_accessible().set_name('Sesi fokus berjalan')
        self.led.get_style_context().add_class('focus-led')
        self.blink_on = False
        self.blink_source = 0
        self.toggle = Gtk.Button()
        self.toggle.connect('clicked', self.toggle_timer)
        self.spin = Gtk.SpinButton.new_with_range(MIN_MINUTES, MAX_MINUTES, 1)
        self.spin.set_tooltip_text('Menit fokus')
        self.spin.get_accessible().set_name('Menit fokus')
        self.spin.set_numeric(True)
        self.initialising = True
        self.minutes = clamp_minutes(minutes) if minutes is not None else duration // 60
        self.spin.set_value(self.minutes)
        self.spin.connect('value-changed', self.on_minutes_changed)
        self.initialising = False
        self.reset = Gtk.Button(label='Reset')
        self.reset.connect('clicked', self.reset_timer)
        self.pack_start(self.label, True, True, 0)
        self.pack_start(self.led, False, False, 0)
        self.pack_start(self.spin, False, False, 0)
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


    def on_minutes_changed(self, spin):
        if getattr(self, 'initialising', False):
            return
        value = clamp_minutes(int(spin.get_value()))
        if value == self.minutes:
            return
        self.minutes = value
        self.duration = value * 60
        if not self.running and self.paused is not None:
            self.paused = float(self.duration)
        self.update()
        self.changed()

    def set_minutes(self, minutes):
        self.spin.set_value(clamp_minutes(minutes))

    def update(self):
        remaining = self.countdown
        base = self.duration if remaining is None else remaining
        self.label.set_text(f'Fokus · {self.format_time(base)}')
        self.toggle.set_label('Jeda' if self.running else 'Mulai' if remaining is None else 'Lanjut')
        self.reset.set_sensitive(remaining is not None)
        self.reset.set_sensitive(remaining is not None)
        if remaining is not None and remaining <= 0:
            self.label.set_text(f'Fokus · {self.format_time(0)}')
        self.led.set_visible(self.running)
        self.refresh_led()
        self.sync_blink()


    def refresh_led(self):
        self.led.set_opacity(1.0 if self.blink_on else 0.22)

    def sync_blink(self):
        if self.running and not self.blink_source:
            self.blink_source = GLib.timeout_add(BLINK_MS, self.blink)
        elif not self.running and self.blink_source:
            GLib.source_remove(self.blink_source)
            self.blink_source = 0
            self.blink_on = False

    def blink(self):
        if not self.running:
            self.blink_source = 0
            return GLib.SOURCE_REMOVE
        self.blink_on = not self.blink_on
        self.refresh_led()
        return GLib.SOURCE_CONTINUE

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
            if not self.paused:
                self.paused = float(self.duration)
            self.deadline = self.clock() + self.paused
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
        remaining = self.countdown
        if remaining is not None and remaining <= 0:
            self.source = 0
            self.deadline = None
            self.paused = 0.0
            self.update()
            self.changed()
            self.finished()
            return GLib.SOURCE_REMOVE
        self.update()
        self.changed()
        return GLib.SOURCE_CONTINUE

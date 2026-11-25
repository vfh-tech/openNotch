import logging
import math

import cairo
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gdk, Gio, GLib, Gtk, GtkLayerShell as Layer, Pango

from agenda_panel import AgendaPanel
from audio import AudioControls
from focus_timer import FocusTimer
from geometry import next_section
from notch_state import Banner, NotchState, Page
from notifications import NotificationMonitor
from outputs import OutputBinding
from settings import NotchSettings

CLOSED_W, CLOSED_H = 108, 18
INSET = 16
WIDTH = 368
PAD_TOP = 12
PAD_BOTTOM = 14
SETTINGS_PATH = GLib.get_user_config_dir() + '/cosmic-tray-notch/notch.json'

CSS = b'''window { background-color: transparent; }
label { color: #ececf1; }
.notice-title { font-weight: bold; }
.notice-meta { color: #a8a8b3; font-size: 11px; }
button { background: transparent; border: 0; box-shadow: none; padding: 4px;
         border-radius: 8px; color: #ececf1; }
button:hover, button:focus { background: rgba(255, 255, 255, 0.09); }
scale { padding: 0 2px; }
.focus-led { font-size: 13px; padding: 0 1px; }
.focus-led.on { color: #33f06b; }
.focus-led.off { color: rgba(51, 240, 107, 0.22); }
stack { background: transparent; }'''


class Notch:
    def __init__(self):
        self.progress = self.target = 0.0
        self.tick = 0
        self.timer = 0
        self.notice_timer = 0
        self.state = NotchState()
        self.config = NotchSettings(SETTINGS_PATH)
        self.section = 'all'
        self.audio = None
        self.flash = 0.0
        self.flash_source = 0
        self.agenda = None
        self.window = Gtk.Window(decorated=False, app_paintable=True, resizable=False)
        screen = self.window.get_screen()
        self.window.set_visual(screen.get_rgba_visual())
        Layer.init_for_window(self.window)
        Layer.set_namespace(self.window, 'cosmic-tray-notch')
        Layer.set_layer(self.window, Layer.Layer.OVERLAY)
        Layer.set_anchor(self.window, Layer.Edge.TOP, True)
        Layer.set_exclusive_zone(self.window, -1)
        Layer.set_keyboard_mode(self.window, Layer.KeyboardMode.ON_DEMAND)
        self.window.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
                               | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.window.connect('enter-notify-event', self.enter)
        self.window.connect('leave-notify-event', self.leave)
        self.window.connect('button-press-event', self.press_background)
        self.window.connect('scroll-event', self.on_scroll)
        self.window.connect('key-press-event', self.key)
        self.window.connect('destroy', Gtk.main_quit)

        self.canvas = Gtk.Fixed()
        self.window.add(self.canvas)
        self.canvas.connect('draw', self.draw)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(screen, provider,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.pages = Gtk.Stack()
        self.pages.set_transition_type(Gtk.StackTransitionType.NONE)
        self.pages.set_size_request(WIDTH - 2 * INSET, -1)
        self.canvas.put(self.pages, INSET, PAD_TOP)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.pages.add_named(self.content, 'content')

        self.banner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.banner_labels = []
        for index in range(3):
            label = Gtk.Label(xalign=0)
            label.set_single_line_mode(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(44)
            if index == 1:
                label.get_style_context().add_class('notice-title')
            self.banner.pack_start(label, False, False, 0)
            self.banner_labels.append(label)
        self.pages.add_named(self.banner, 'banner')

        self.focus = FocusTimer(self.content_changed, self.focus_complete, WIDTH - 2 * INSET)
        self.audio = AudioControls(self.content_changed, WIDTH - 2 * INSET)
        self.agenda = AgendaPanel(self.content_changed, WIDTH - 2 * INSET)
        for widget in (self.focus, self.audio, self.agenda):
            self.content.pack_start(widget, False, False, 0)

        self.notifications = NotificationMonitor(self.show_notice)
        self.output = OutputBinding(self.window.get_display(), self.window, self.output_changed)
        self.apply_config()
        self.window.show_all()
        self.sync_page()

    def apply_config(self):
        for widget, name in ((self.audio, 'media'), (self.agenda, 'agenda')):
            if widget is not None:
                widget.set_visible(self.section_visible(name))

    def section_visible(self, name):
        return self.section in ('all', name) and self.config[f'show_{name}']

    def content_changed(self):
        self.apply_config()
        self.canvas.set_size_request(WIDTH, self.open_height())
        self.canvas.queue_resize()
        self.frame()

    def page_height(self):
        page = self.banner if self.displayed_banner is not None else self.content
        _, natural = page.get_preferred_height_for_width(WIDTH - 2 * INSET)
        return max(CLOSED_H, natural + PAD_TOP + PAD_BOTTOM)

    def open_height(self):
        return self.page_height()

    @property
    def displayed_banner(self):
        return self.state.banner or self.state.outgoing

    def geometry(self):
        high = self.page_height()
        return (round(CLOSED_W + (WIDTH - CLOSED_W) * self.progress),
                round(CLOSED_H + (high - CLOSED_H) * self.progress))

    def output_changed(self, mapped):
        self.state.set_output(mapped)
        if not mapped:
            if self.tick:
                self.window.remove_tick_callback(self.tick)
                self.tick = 0
            self.progress = self.target = 0.0
            logging.info('Waiting for a Wayland output')
        else:
            logging.info('COSMIC notch ready')
            self.show_queued_banner()
        self.sync_page()

    def on_scroll(self, _widget, event):
        if not self.config['scroll_navigation']:
            return False
        if event.direction not in (Gdk.ScrollDirection.UP, Gdk.ScrollDirection.DOWN):
            return False
        enabled = {'media': self.config['show_media'], 'agenda': self.config['show_agenda']}
        self.section = next_section(self.section, enabled)
        self.content_changed()
        return True

    def draw(self, _widget, ctx):
        w, h = self.geometry()
        left = (WIDTH - w) / 2
        right = left + w
        radius = min(16, h * .55)
        ctx.set_source_rgb(.045, .045, .057)
        accent = self.flash
        base = (0.045, 0.045, 0.057)
        blend = (base[0] + (0.30 - base[0]) * accent,
                 base[1] + (0.62 - base[1]) * accent,
                 base[2] + (0.38 - base[2]) * accent)
        ctx.set_source_rgb(*blend)
        ctx.move_to(left, 0)
        ctx.line_to(right, 0)
        ctx.line_to(right, h - radius)
        ctx.arc(right - radius, h - radius, radius, 0, math.pi / 2)
        ctx.arc(left + radius, h - radius, radius, math.pi / 2, math.pi)
        ctx.close_path()
        ctx.fill()
        if self.progress < .85:
            remaining = self.focus.countdown
            if accent > 0.02:
                ctx.set_source_rgba(0.55, 1.0, 0.72, accent)
                ctx.arc(WIDTH / 2, CLOSED_H / 2, 3.5, 0, math.tau)
                ctx.fill()
            elif remaining is None:
                ctx.set_source_rgba(.92, .92, .96, 1 - self.progress)
                ctx.arc(WIDTH / 2, CLOSED_H / 2, 2, 0, math.tau)
                ctx.fill()
            else:
                ctx.set_source_rgba(.92, .92, .96, 1 - self.progress)
                text = self.focus.format_time(remaining)
                ctx.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                ctx.set_font_size(11)
                bounds = ctx.text_extents(text)
                shift = -7 if self.focus.running else 0
                ctx.move_to((WIDTH - bounds.width) / 2 - bounds.x_bearing + shift,
                            (CLOSED_H - bounds.height) / 2 - bounds.y_bearing)
                ctx.show_text(text)
                if self.focus.running:
                    ctx.set_source_rgba(0.20, 0.94, 0.42,
                                        1.0 if self.focus.blink_on else 0.22)
                    ctx.arc((WIDTH + bounds.width) / 2 + 7, CLOSED_H / 2, 2.6, 0, math.tau)
                    ctx.fill()
        return False

    def frame(self):
        w, h = self.geometry()
        visible = self.progress > .92
        showing_banner = self.displayed_banner is not None
        banner_page = 'banner' if showing_banner else 'content'
        if self.pages.get_visible_child_name() != banner_page:
            self.pages.set_visible_child_name(banner_page)
        self.apply_config()
        self.content.set_visible(visible and not showing_banner)
        self.banner.set_visible(visible and showing_banner)
        self.canvas.set_size_request(WIDTH, self.page_height())
        surface = self.window.get_window()
        if surface:
            surface.input_shape_combine_region(
                cairo.Region(cairo.RectangleInt((WIDTH - w) // 2, 0, w, h)), 0, 0)
        self.canvas.queue_draw()

    def animate(self, opened):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        target = float(opened)
        if target == self.target:
            return False
        self.target, origin = target, self.progress
        if not self.window.get_mapped():
            self.progress = target
            self.state.outgoing = None
            self.frame()
            return False
        start = GLib.get_monotonic_time()
        if self.tick:
            self.window.remove_tick_callback(self.tick)

        def step(_widget, _clock):
            elapsed = min(1, (GLib.get_monotonic_time() - start) / 240_000)
            eased = 1 - (1 - elapsed) ** 3
            self.progress = origin + (target - origin) * eased
            self.frame()
            if elapsed >= 1:
                self.tick = 0
                if not target:
                    self.state.outgoing = None
            return elapsed < 1

        self.tick = self.window.add_tick_callback(step)
        return False

    def sync_page(self):
        self.animate(self.state.page in (Page.TRAY, Page.BANNER))
        self.frame()

    def focus_complete(self):
        self.play_alert()
        self.state.queued = Banner('Timer Fokus', 'Waktu fokus selesai',
                                  'Ambil jeda sebelum sesi berikutnya.')
        self.show_queued_banner()

    def play_alert(self):
        self.flash = 1.0
        if self.flash_source:
            GLib.source_remove(self.flash_source)
        ticks = [0.85, 0.6, 0.35, 0.12, 0.0]

        def step():
            self.flash = ticks.pop(0)
            self.frame()
            if not ticks:
                self.flash_source = 0
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        self.flash_source = GLib.timeout_add(160, step)
        try:
            Gio.Subprocess.new(['paplay', '/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga'],
                               Gio.SubprocessFlags.STDERR_SILENCE | Gio.SubprocessFlags.STDOUT_SILENCE)
        except GLib.Error as exc:
            logging.debug('Alert sound unavailable: %s', exc)

    def show_queued_banner(self):
        banner = self.state.take_queued()
        if banner is not None:
            self.show_notice(banner.app, banner.title, banner.body)

    def show_notice(self, app, title, body):
        if self.notice_timer:
            GLib.source_remove(self.notice_timer)
        self.state.show(Banner(app, title, body))
        for label, text in zip(self.banner_labels, (app, title, body)):
            label.set_text(text)
        self.notice_timer = GLib.timeout_add(5500, self.expire_notice)
        self.sync_page()

    def expire_notice(self):
        self.notice_timer = 0
        self.dismiss_notice()
        return GLib.SOURCE_REMOVE

    def dismiss_notice(self):
        if self.notice_timer:
            GLib.source_remove(self.notice_timer)
            self.notice_timer = 0
        self.state.dismiss(animate=True)
        self.show_queued_banner()
        self.sync_page()

    def press_background(self, _widget, event):
        if event.button == 1 and self.state.banner is not None:
            self.dismiss_notice()
            return True
        self.state.manual = True
        self.sync_page()
        return False

    def enter(self, _widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.state.hover = True
            self.state.outgoing = None
            if self.state.banner is None:
                self.audio.refresh()
            self.sync_page()
        return False

    def leave(self, _widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.state.hover = self.state.manual = False
            self.schedule_close()
        return False

    def schedule_close(self):
        if self.state.page is not Page.CLOSED or self.timer:
            return

        def close():
            self.timer = 0
            self.sync_page()
            return GLib.SOURCE_REMOVE

        self.timer = GLib.timeout_add(300, close)

    def key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.state.hover = self.state.manual = False
            self.dismiss_notice()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_space) and not self.target:
            self.state.manual = True
            self.sync_page()
            return True
        return False


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    if not Layer.is_supported():
        raise SystemExit('Wayland layer shell is unavailable')
    Notch()
    Gtk.main()

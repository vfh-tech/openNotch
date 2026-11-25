import logging
import math

import cairo
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
gi.require_version('DbusmenuGtk3', '0.4')
from gi.repository import DbusmenuGtk3, Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkLayerShell as Layer, Pango

from audio import AudioControls
from focus_timer import FocusTimer
from agenda_panel import AgendaPanel
from shelf_panel import ShelfPanel
from notch_state import Banner, NotchState, Page
from notifications import NotificationMonitor
from outputs import OutputBinding
SHELF_PATH = GLib.get_user_config_dir() + '/cosmic-tray-notch/shelf.json'

WATCHER = 'org.kde.StatusNotifierWatcher'
ITEM = 'org.kde.StatusNotifierItem'
CLOSED_W, CLOSED_H = 108, 18
COLS, CELL, INSET = 8, 42, 16
WIDTH = COLS * CELL + 2 * INSET


class Tray:
    def __init__(self, grid, changed, menu_open):
        self.grid, self.changed, self.menu_open = grid, changed, menu_open
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.host = 'org.kde.StatusNotifierHost-{}'.format(
            self.bus.get_unique_name().removeprefix(':').replace('.', '-'))
        self.bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
                           'RequestName', GLib.Variant('(su)', (self.host, 4)), None,
                           Gio.DBusCallFlags.NONE, 1500, None)
        self.items = {}
        self.watcher = Gio.DBusProxy.new_sync(self.bus, Gio.DBusProxyFlags.NONE, None,
                                             WATCHER, '/StatusNotifierWatcher', WATCHER)
        self.watcher.connect('g-properties-changed', self.schedule)
        self.watcher.connect('g-signal', self.watch_signal)
        self.watcher.connect('notify::g-name-owner', self.register_host)
        self.pending = 0
        self.register_host()
        self.sync()

    def schedule(self, *_):
        if not self.pending:
            self.pending = GLib.idle_add(self.sync)

    def register_host(self, *_):
        if self.watcher.get_name_owner():
            self.invoke(self.watcher, 'RegisterStatusNotifierHost', GLib.Variant('(s)', (self.host,)))
        self.schedule()

    def watch_signal(self, _proxy, _sender, member, parameters):
        if member not in ('StatusNotifierItemRegistered', 'StatusNotifierItemUnregistered'):
            return
        registered = self.watcher.get_cached_property('RegisteredStatusNotifierItems')
        ids = set(registered.unpack()) if registered is not None else set()
        (key,) = parameters.unpack()
        if member == 'StatusNotifierItemRegistered':
            ids.add(key)
        else:
            ids.discard(key)
        self.watcher.set_cached_property('RegisteredStatusNotifierItems', GLib.Variant('as', sorted(ids)))
        self.schedule()

    def sync(self):
        self.pending = 0
        registered = self.watcher.get_cached_property('RegisteredStatusNotifierItems')
        ids = registered.unpack() if registered is not None else []
        for key in list(self.items):
            if key not in ids:
                self.items.pop(key)[1].destroy()
        for key in ids:
            if key not in self.items:
                self.add(key)
        for button in self.grid.get_children():
            self.grid.remove(button)
        for i, (_, button) in enumerate(self.items.values()):
            self.grid.attach(button, i % COLS, i // COLS, 1, 1)
            button.show()
        self.changed(len(self.items))
        return GLib.SOURCE_REMOVE

    def add(self, key):
        name, sep, path = key.partition('/')
        proxy = Gio.DBusProxy.new_sync(self.bus, Gio.DBusProxyFlags.DO_NOT_AUTO_START, None,
                                       name, sep + path if sep else '/StatusNotifierItem', ITEM)
        button = Gtk.Button()
        button.set_size_request(CELL, CELL)
        button.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        button.connect('button-press-event', self.press, proxy)
        button.connect('scroll-event', self.scroll, proxy)
        button.connect('clicked', lambda widget: self.activate(widget, proxy, None))
        proxy.connect('g-properties-changed', lambda *_: self.update_icon(button, proxy))
        proxy.connect('g-signal', lambda *_: self.reload_icon(button, proxy))
        self.items[key] = (proxy, button)
        self.update_icon(button, proxy)

    @staticmethod
    def prop(proxy, name, default=None):
        value = proxy.get_cached_property(name)
        return value.unpack() if value is not None else default

    def reload_icon(self, button, proxy):
        def done(bus, result):
            try:
                values = bus.call_finish(result).get_child_value(0)
                for i in range(values.n_children()):
                    entry = values.get_child_value(i)
                    proxy.set_cached_property(entry.get_child_value(0).get_string(),
                                              entry.get_child_value(1).get_variant())
                if button.get_parent() is not None:
                    self.update_icon(button, proxy)
            except GLib.Error as exc:
                logging.debug('Tray icon disappeared: %s', exc)
        self.bus.call(proxy.get_name(), proxy.get_object_path(), 'org.freedesktop.DBus.Properties',
                      'GetAll', GLib.Variant('(s)', (ITEM,)), None,
                      Gio.DBusCallFlags.NO_AUTO_START, 1500, None, done)

    def update_icon(self, button, proxy):
        attention = self.prop(proxy, 'Status') == 'NeedsAttention'
        icon = self.prop(proxy, 'AttentionIconName' if attention else 'IconName')
        pixmaps = self.prop(proxy, 'AttentionIconPixmap' if attention else 'IconPixmap', [])
        if attention and not icon and not pixmaps:
            icon, pixmaps = self.prop(proxy, 'IconName'), self.prop(proxy, 'IconPixmap', [])
        image = Gtk.Image()
        if icon and not icon.startswith('/'):
            theme = Gtk.IconTheme.get_default()
            custom = self.prop(proxy, 'IconThemePath')
            if custom:
                theme = Gtk.IconTheme.new()
                theme.set_search_path([custom, *Gtk.IconTheme.get_default().get_search_path()])
            try:
                image.set_from_pixbuf(theme.load_icon(icon, 22, Gtk.IconLookupFlags.FORCE_SIZE))
            except GLib.Error:
                pass
        elif icon:
            try:
                image.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(icon, 22, 22, True))
            except GLib.Error:
                pass
        if image.get_storage_type() == Gtk.ImageType.EMPTY and pixmaps:
            for w, h, data in sorted(pixmaps, key=lambda item: abs(max(item[:2]) - 22)):
                if not (0 < w <= 512 and 0 < h <= 512 and len(data) == 4 * w * h):
                    continue
                argb = bytes(data)
                rgba = bytearray(len(argb))
                rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = argb[1::4], argb[2::4], argb[3::4], argb[0::4]
                pix = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(bytes(rgba)), GdkPixbuf.Colorspace.RGB,
                                                       True, 8, w, h, 4 * w)
                image.set_from_pixbuf(pix.scale_simple(max(1, round(22 * w / max(w, h))),
                                                        max(1, round(22 * h / max(w, h))), GdkPixbuf.InterpType.BILINEAR))
                break
        if image.get_storage_type() == Gtk.ImageType.EMPTY:
            image.set_from_icon_name('application-x-executable-symbolic', Gtk.IconSize.BUTTON)
        image.show()
        name = self.prop(proxy, 'Title') or self.prop(proxy, 'Id') or proxy.get_name()
        button.set_image(image)
        button.set_tooltip_text(name)
        button.get_accessible().set_name(name)

    def invoke(self, proxy, method, args):
        def done(obj, result):
            try:
                obj.call_finish(result)
            except GLib.Error as exc:
                logging.debug('%s failed for %s: %s', method, proxy.get_name(), exc)
        proxy.call(method, args, Gio.DBusCallFlags.NO_AUTO_START, 1500, None, done)

    def context(self, button, proxy, event):
        path = self.prop(proxy, 'Menu')
        if path and path != '/':
            menu = DbusmenuGtk3.Menu.new(proxy.get_name(), path)
            self.menu_open(menu)
            menu.popup_at_widget(button, Gdk.Gravity.SOUTH, Gdk.Gravity.NORTH, event)
        else:
            self.invoke(proxy, 'ContextMenu', self.point(event))

    @staticmethod
    def point(event):
        return GLib.Variant('(ii)', (int(event.x_root), int(event.y_root)) if event else (0, 0))

    def activate(self, button, proxy, event):
        if self.prop(proxy, 'ItemIsMenu', False):
            self.context(button, proxy, event)
        else:
            self.invoke(proxy, 'Activate', self.point(event))

    def press(self, button, event, proxy):
        if event.button == 1:
            self.activate(button, proxy, event)
        elif event.button == 3:
            self.context(button, proxy, event)
        elif event.button == 2:
            self.invoke(proxy, 'SecondaryActivate', self.point(event))
        else:
            return False
        return True

    def scroll(self, _button, event, proxy):
        deltas = {Gdk.ScrollDirection.UP: (120, 'vertical'), Gdk.ScrollDirection.DOWN: (-120, 'vertical'),
                  Gdk.ScrollDirection.LEFT: (-120, 'horizontal'), Gdk.ScrollDirection.RIGHT: (120, 'horizontal')}
        value = deltas.get(event.direction)
        if value is None:
            _, dx, dy = event.get_scroll_deltas()
            value = (round(-120 * dy), 'vertical') if abs(dy) >= abs(dx) else (round(120 * dx), 'horizontal')
        if value[0]:
            self.invoke(proxy, 'Scroll', GLib.Variant('(is)', value))
        return True


class Notch:
    def __init__(self):
        self.progress = self.target = 0.0
        self.tick = self.timer = 0
        self.notice_timer = 0
        self.state = NotchState()
        self.agenda = None
        self.shelf = None
        self.count = 0
        self.height = 74
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
                               | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.window.connect('enter-notify-event', self.enter)
        self.window.connect('leave-notify-event', self.leave)
        self.window.connect('button-press-event', self.press_background)
        self.window.connect('key-press-event', self.key)
        self.window.connect('destroy', Gtk.main_quit)
        self.canvas = Gtk.Fixed()
        self.canvas.set_size_request(WIDTH, 104)
        self.window.add(self.canvas)
        self.canvas.connect('draw', self.draw)
        self.grid = Gtk.Grid()
        self.empty = Gtk.Label(label='Tidak ada ikon tray')
        self.empty.set_size_request(180, 34)
        self.canvas.put(self.empty, (WIDTH - 180) // 2, 28)
        self.canvas.put(self.grid, 0, 24)
        self.notice_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.notice_box.set_size_request(WIDTH - 40, 80)
        self.notice_labels = []
        for index in range(3):
            label = Gtk.Label(xalign=0)
            label.set_single_line_mode(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(48)
            if index == 1:
                label.get_style_context().add_class('notice-title')
            self.notice_box.pack_start(label, False, False, 0)
            self.notice_labels.append(label)
        self.canvas.put(self.notice_box, 20, 13)
        css = Gtk.CssProvider()
        css.load_from_data(b'window { background-color: transparent; } label { color: #eee; } .notice-title { font-weight: bold; } .notice-meta { color: #b9b9c0; font-size: 11px; } button { background: transparent; border: 0; box-shadow: none; padding: 4px; border-radius: 9px; color: #fafafa; } button:hover, button:focus { background: #34343b; } scale { padding: 0 2px; }')
        Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.focus = FocusTimer(self.canvas.queue_draw, self.focus_complete, WIDTH - 2 * INSET)
        self.canvas.put(self.focus, INSET, 0)
        self.audio = None
        self.audio = AudioControls(self.layout_audio, WIDTH - 2 * INSET)
        self.canvas.put(self.audio, INSET, 0)
        self.layout_audio()
        self.agenda = AgendaPanel(self.layout_audio, WIDTH - 2 * INSET)
        self.canvas.put(self.agenda, INSET, 0)
        self.layout_audio()
        self.shelf = ShelfPanel(self.layout_audio, WIDTH - 2 * INSET, SHELF_PATH)
        self.canvas.put(self.shelf, INSET, 0)
        self.layout_audio()
        self.tray = Tray(self.grid, self.on_items, self.hold_menu)
        self.notifications = NotificationMonitor(self.show_notice)
        self.output = OutputBinding(self.window.get_display(), self.window, self.output_changed)

    def output_changed(self, mapped):
        self.state.set_output(mapped)
        if not mapped:
            if self.tick:
                self.window.remove_tick_callback(self.tick)
                self.tick = 0
            self.progress = self.target = 0.0
            logging.info('Waiting for a Wayland output')
        else:
            logging.info('COSMIC tray notch ready: %d registered apps', self.count)
            self.show_queued_banner()
        self.sync_page()

    def on_items(self, count):
        self.count = count
        self.height = 32 + CELL * max(1, math.ceil(count / COLS))
        self.canvas.move(self.grid, (WIDTH - CELL * min(count, COLS)) // 2, 24)
        self.layout_audio()

    def layout_audio(self):
        if self.audio is None:
            return
        self.canvas.move(self.audio, INSET, self.height)
        self.canvas.move(self.focus, INSET, self.open_height() - 44)
        self.canvas.set_size_request(WIDTH, max(104, self.open_height()))
        self.frame()
        if self.agenda is not None:
            self.canvas.move(self.agenda, INSET, self.height + 68 + (68 if self.audio and self.audio.media.get_visible() else 0))
        if self.shelf is not None:
            offset = self.height + 68 + (68 if self.audio and self.audio.media.get_visible() else 0)
            offset += self.agenda.height if self.agenda is not None else 0
            self.canvas.move(self.shelf, INSET, offset)

    def open_height(self):
        media = 68 if self.audio and self.audio.media.get_visible() else 0
        agenda = self.agenda.height if self.agenda is not None else 0
        shelf = self.shelf.height if self.shelf is not None else 0
        return self.height + 88 + media + agenda + shelf

    def geometry(self):
        high = 104 if self.displayed_banner else self.open_height()
        return (round(CLOSED_W + (WIDTH - CLOSED_W) * self.progress),
                round(CLOSED_H + (high - CLOSED_H) * self.progress))

    @property
    def displayed_banner(self):
        return self.state.banner or self.state.outgoing

    def draw(self, _widget, ctx):
        w, h = self.geometry()
        left = (WIDTH - w) / 2
        right = left + w
        r = min(16, h * .55)
        ctx.set_source_rgb(.045, .045, .057)
        ctx.move_to(left, 0)
        ctx.line_to(right, 0)
        ctx.line_to(right, h - r)
        ctx.arc(right - r, h - r, r, 0, math.pi / 2)
        ctx.arc(left + r, h - r, r, math.pi / 2, math.pi)
        ctx.close_path()
        ctx.fill()
        if self.progress < .85:
            remaining = self.focus.countdown
            ctx.set_source_rgba(.9, .9, .94, 1 - self.progress)
            if remaining is None:
                ctx.arc(WIDTH / 2, 9, 2, 0, math.tau)
                ctx.fill()
            else:
                text = self.focus.format_time(remaining)
                ctx.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                ctx.set_font_size(11)
                bounds = ctx.text_extents(text)
                ctx.move_to((WIDTH - bounds.width) / 2 - bounds.x_bearing,
                            (CLOSED_H - bounds.height) / 2 - bounds.y_bearing)
                ctx.show_text(text)
        return False

    def frame(self):
        w, h = self.geometry()
        visible = self.progress > .92
        tray_visible = visible and not self.displayed_banner
        self.grid.set_visible(tray_visible and bool(self.count))
        self.empty.set_visible(tray_visible and not self.count)
        if self.audio is not None:
            self.audio.set_visible(tray_visible)
        self.notice_box.set_visible(visible and self.displayed_banner is not None)
        self.focus.set_visible(tray_visible)
        if self.agenda is not None:
            self.agenda.set_visible(tray_visible)
        if self.shelf is not None:
            self.shelf.set_visible(tray_visible)
        surface = self.window.get_window()
        if surface:
            surface.input_shape_combine_region(cairo.Region(cairo.RectangleInt((WIDTH - w) // 2, 0, w, h)), 0, 0)
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
            t = min(1, (GLib.get_monotonic_time() - start) / 240_000)
            eased = 1 - (1 - t) ** 3
            self.progress = origin + (target - origin) * eased
            self.frame()
            if t >= 1:
                self.tick = 0
                if not target:
                    self.state.outgoing = None
            return t < 1
        self.tick = self.window.add_tick_callback(step)
        return False

    def sync_page(self):
        self.animate(self.state.page in (Page.TRAY, Page.BANNER))
        self.frame()

    def focus_complete(self):
        self.state.queued = Banner('Timer Fokus', 'Waktu fokus selesai',
                                  'Ambil jeda sebelum sesi berikutnya.')
        self.show_queued_banner()

    def show_queued_banner(self):
        banner = self.state.take_queued()
        if banner is not None:
            self.show_notice(banner.app, banner.title, banner.body)

    def show_notice(self, app, title, body):
        if self.notice_timer:
            GLib.source_remove(self.notice_timer)
        self.state.show(Banner(app, title, body))
        for label, text in zip(self.notice_labels, (app, title, body)):
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

    def hold_menu(self, menu):
        self.state.menu = True
        def done(*_):
            self.state.menu = False
            self.schedule_close()
        menu.connect('deactivate', done)

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
    notch = Notch()
    Gtk.main()

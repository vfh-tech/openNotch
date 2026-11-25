import os
import subprocess
from types import SimpleNamespace

from notch import Gdk, Gio, GLib, Gtk, Notch


def main():
    notch = Notch()
    display = notch.window.get_display()
    monitor = display.get_monitor(0)
    assert monitor is not None, 'Needs an active Wayland monitor'
    notch.output.display = SimpleNamespace(
        get_n_monitors=lambda: int(connected),
        get_monitor=lambda _: monitor,
        get_primary_monitor=lambda: monitor if connected else None,
    )
    connected = True
    event = SimpleNamespace(detail=Gdk.NotifyType.NONLINEAR)
    errors = []
    checks = []

    def at(ms):
        def enqueue(action):
            def run():
                try:
                    action()
                    checks.append(action.__name__)
                except Exception as error:
                    errors.append((action.__name__, repr(error)))
                    Gtk.main_quit()
                return GLib.SOURCE_REMOVE
            GLib.timeout_add(ms, run)
        return enqueue

    @at(400)
    def hover():
        assert notch.window.get_mapped()
        notch.enter(None, event)

    @at(800)
    def notification():
        assert notch.grid.get_mapped() and notch.count > 0
        notch.focus.toggle.clicked()
        proxy = next(p for p, _ in notch.tray.items.values() if notch.tray.prop(p, 'Menu') not in ('/', None))
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        bus.call_sync(proxy.get_name(), notch.tray.prop(proxy, 'Menu'), 'com.canonical.dbusmenu',
                      'GetLayout', GLib.Variant('(iias)', (0, 1, [])), None,
                      Gio.DBusCallFlags.NO_AUTO_START, 1500, None)
        bus.call_sync('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                      'org.freedesktop.Notifications', 'Notify', GLib.Variant('(susssasa{sv}i)',
                      ('Notch test', 0, '', 'Review PR-01', 'Wayland interaction check', [],
                       {'transient': GLib.Variant('b', True)}, 1200)), None,
                      Gio.DBusCallFlags.NONE, 1500, None)

    @at(1350)
    def banner_preempts_tray():
        assert notch.notice_box.get_mapped() and not notch.grid.get_mapped()
        assert notch.notice_labels[1].get_text() == 'Review PR-01'
        if (output := os.environ.get('NOTCH_TEST_SCREENSHOT_DIR')):
            subprocess.Popen(['cosmic-screenshot', '--interactive=false', '--modal=false',
                              '--notify=false', '--save-dir', output])

    @at(1700)
    def dismiss_keeps_hover():
        notch.press_background(None, SimpleNamespace(button=1))
        assert notch.grid.get_mapped() and not notch.notice_box.get_mapped()
        assert notch.focus.running
        notch.leave(None, event)

    @at(2350)
    def detach():
        nonlocal connected
        assert notch.geometry() == (108, 18)
        connected = False
        notch.output.schedule()

    @at(2700)
    def reconnect():
        nonlocal connected
        assert not notch.window.get_realized()
        connected = True
        notch.output.schedule()

    @at(3150)
    def remapped():
        assert notch.window.get_mapped() and 0 < notch.focus.countdown < 1500
        Gtk.main_quit()

    Gtk.main()
    assert not errors, errors
    assert checks[-1:] == ['remapped'], checks
    print('Wayland simulation:', ', '.join(checks))


if __name__ == '__main__':
    main()

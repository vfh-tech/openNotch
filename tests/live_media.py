import os
import subprocess
import sys
from types import SimpleNamespace

from notch import Gdk, GLib, Gtk, Notch

FIXTURE = os.environ.get('MPRIS_FIXTURE_NAME', 'NotchProbeA')
OTHER = os.environ.get('MPRIS_FIXTURE_OTHER', 'NotchProbeB')
SCREENSHOT = os.environ.get('NOTCH_TEST_SCREENSHOT_DIR')


def main():
    notch = Notch()
    audio = notch.audio
    event = SimpleNamespace(detail=Gdk.NotifyType.NONLINEAR)
    steps = []

    def run(name, action):
        try:
            action()
            steps.append(name)
        except Exception as exc:  # noqa: BLE001 - reported verbatim
            print(f'FAIL {name}: {exc!r}', flush=True)
            Gtk.main_quit()
            raise SystemExit(1) from exc

    def wait_for_fixture(attempt=0):
        names = [str(p.props.player_name) for p in audio.manager.props.players]
        if FIXTURE in names and OTHER in names:
            audio.prefer_player(None, FIXTURE)
            run('select_fixture', lambda: _assert_selected())
            notch.enter(None, event)
            GLib.timeout_add(800, check_media)
            return GLib.SOURCE_REMOVE
        if attempt >= 60:
            print(f'FAIL fixture players missing: {names}', flush=True)
            raise SystemExit(1)
        GLib.timeout_add(100, lambda: wait_for_fixture(attempt + 1))
        return GLib.SOURCE_REMOVE

    def _assert_selected():
        assert audio.model.selected == FIXTURE, audio.model.selected
        assert audio.player is not None
        assert str(audio.player.props.player_name) == FIXTURE

    def check_media():
        def body():
            assert audio.get_mapped(), 'audio panel hidden'
            assert audio.media.get_mapped(), 'media row hidden'
            assert audio.title.get_text() == 'Lagu Satu', audio.title.get_text()
            assert audio.artist.get_text() == 'Notch Player', audio.artist.get_text()
            assert audio.cover.get_storage_type() == Gtk.ImageType.PIXBUF, 'artwork missing'
            assert audio.elapsed.get_text() == '0:42 / 3:00', audio.elapsed.get_text()
            assert audio.players.get_visible(), 'player selector hidden'
        run('media', body)
        GLib.timeout_add(300, do_seek)
        return GLib.SOURCE_REMOVE

    def do_seek():
        run('seek', lambda: audio.seek(audio.progress, 0, 90_000_000))
        GLib.timeout_add(700, do_switch)

    def do_switch():
        def body():
            audio.prefer_player(None, OTHER)
            assert audio.model.selected == OTHER, audio.model.selected
            assert audio.title.get_text() == 'Lagu Satu'
        run('switch', body)
        if SCREENSHOT:
            subprocess.Popen(['cosmic-screenshot', '--interactive=false', '--modal=false',
                              '--notify=false', '--save-dir', SCREENSHOT])
        GLib.timeout_add(700, do_hide)

    def do_hide():
        notch.leave(None, event)
        GLib.timeout_add(1000, do_done)

    def do_done():
        def body():
            assert not audio.active, 'controls stayed active'
            assert not notch.window.get_mapped() or notch.geometry() == (108, 18), notch.geometry()
        run('done', body)
        Gtk.main_quit()

    GLib.timeout_add(300, lambda: wait_for_fixture())
    Gtk.main()
    print('Media probe:', ', '.join(steps))


if __name__ == '__main__':
    sys.exit(main())
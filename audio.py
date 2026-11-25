import logging
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import gi

gi.require_version('Playerctl', '2.0')
from gi.repository import GdkPixbuf, Gio, GLib, Gtk, Pango, Playerctl

SINK = '@DEFAULT_AUDIO_SINK@'
VOLUME = ('wpctl', 'get-volume', SINK)


def icon_button(icon, label, clicked):
    button = Gtk.Button()
    button.set_size_request(32, 32)
    button.get_accessible().set_name(label)
    button.set_tooltip_text(label)
    button.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
    button.connect('clicked', clicked)
    return button


class AudioControls(Gtk.Box):
    def __init__(self, resized, width):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_size_request(width, -1)
        self.resized = resized
        self.player = None
        self.art_url = None
        self.volume = None
        self.busy = False

        self.media = Gtk.Box(spacing=6)
        self.cover = Gtk.Image.new_from_icon_name('audio-x-generic-symbolic', Gtk.IconSize.BUTTON)
        self.cover.set_size_request(36, 36)
        self.media.pack_start(self.cover, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text.set_valign(Gtk.Align.CENTER)
        self.title, self.artist = Gtk.Label(xalign=0), Gtk.Label(xalign=0)
        for label in (self.title, self.artist):
            label.set_single_line_mode(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_width_chars(1)
            text.pack_start(label, False, False, 0)
        self.title.get_style_context().add_class('notice-title')
        self.media.pack_start(text, True, True, 0)
        self.previous = icon_button('media-skip-backward-symbolic', 'Lagu sebelumnya',
                                    lambda *_: self.transport('Previous'))
        self.play = icon_button('media-playback-start-symbolic', 'Putar atau jeda',
                                lambda *_: self.transport('PlayPause'))
        self.next = icon_button('media-skip-forward-symbolic', 'Lagu berikutnya',
                                lambda *_: self.transport('Next'))
        for button in (self.previous, self.play, self.next):
            button.set_valign(Gtk.Align.CENTER)
            self.media.pack_start(button, False, False, 0)
        self.media.set_size_request(-1, 48)
        self.pack_start(self.media, False, False, 0)

        self.sound = Gtk.Box(spacing=6)
        self.sound.set_size_request(-1, 34)
        self.mute = icon_button('audio-volume-muted-symbolic', 'Bisukan atau nyalakan suara',
                                lambda *_: self.set_volume('set-mute', 'toggle'))
        self.lower = icon_button('list-remove-symbolic', 'Turunkan volume',
                                 lambda *_: self.set_volume('set-volume', '5%-'))
        self.raise_ = icon_button('list-add-symbolic', 'Naikkan volume',
                                  lambda *_: self.set_volume('set-volume', '5%+'))
        self.level = Gtk.Label(label='Volume tidak tersedia', xalign=0)
        self.sound.pack_start(self.mute, False, False, 0)
        self.sound.pack_start(self.level, True, True, 0)
        for button in (self.lower, self.raise_):
            self.sound.pack_start(button, False, False, 0)
        self.pack_start(self.sound, False, False, 0)
        self.media.show_all()
        self.media.set_no_show_all(True)
        self.manager = Playerctl.PlayerManager()
        self.manager.connect('name-appeared', self.add_player)
        self.manager.connect('player-vanished', self.select_player)
        for name in self.manager.props.player_names:
            self.add_player(self.manager, name)
        self.select_player()
        self.update_volume()

    def add_player(self, manager, name):
        try:
            player = Playerctl.Player.new_from_name(name)
            player.connect('playback-status', self.select_player)
            player.connect('metadata', self.select_player)
            for prop in ('can-control', 'can-play', 'can-pause', 'can-go-next', 'can-go-previous'):
                player.connect(f'notify::{prop}', self.select_player)
            manager.manage_player(player)
            self.select_player()
        except GLib.Error as exc:
            logging.debug('MPRIS player unavailable: %s', exc)

    def select_player(self, *_):
        players = self.manager.props.players
        self.player = next((p for p in players if p.props.playback_status == Playerctl.PlaybackStatus.PLAYING),
                           players[0] if players else None)
        player = self.player
        if player:
            self.title.set_text(player.get_title() or player.props.player_name)
            self.artist.set_text(player.get_artist() or player.props.player_name)
            playing = player.props.playback_status == Playerctl.PlaybackStatus.PLAYING
            self.play.get_image().set_from_icon_name('media-playback-pause-symbolic' if playing else
                                                      'media-playback-start-symbolic', Gtk.IconSize.BUTTON)
            self.play.set_sensitive(player.props.can_control and (player.props.can_pause if playing else player.props.can_play))
            self.previous.set_sensitive(player.props.can_control and player.props.can_go_previous)
            self.next.set_sensitive(player.props.can_control and player.props.can_go_next)
            metadata = player.props.metadata
            art = metadata.lookup_value('mpris:artUrl', GLib.VariantType.new('s')) if metadata else None
            self.set_art(art.get_string() if art else None)
        self.media.set_visible(player is not None)
        self.resized()

    def set_art(self, url):
        if url == self.art_url:
            return
        self.art_url = url
        self.cover.set_from_icon_name('audio-x-generic-symbolic', Gtk.IconSize.BUTTON)
        if not url:
            return
        try:
            parsed = urlsplit(url)
            if parsed.scheme == 'file' and parsed.netloc in ('', 'localhost'):
                path = Path(unquote(parsed.path))
                if path.is_file() and path.stat().st_size <= 8 * 1024 * 1024:
                    self.cover.set_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), 34, 34, True))
        except (GLib.Error, OSError, ValueError) as exc:
            logging.debug('MPRIS artwork unavailable: %s', exc)

    def transport(self, method):
        player = self.player
        if player is None:
            return
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        bus.call(f'org.mpris.MediaPlayer2.{player.props.player_instance}', '/org/mpris/MediaPlayer2',
                 'org.mpris.MediaPlayer2.Player', method, None, None,
                 Gio.DBusCallFlags.NO_AUTO_START, 1500, None, self.transport_done)

    @staticmethod
    def transport_done(bus, result):
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            logging.debug('MPRIS action unavailable: %s', exc)

    def refresh(self):
        if not self.busy:
            self.read_volume()

    def set_volume(self, command, value):
        if not self.busy and self.volume is not None:
            args = ('wpctl', command, '-l', '1.0', SINK, value) if command == 'set-volume' else ('wpctl', command, SINK, value)
            self.run(args, lambda _: self.read_volume())

    def read_volume(self):
        def received(output):
            match = re.fullmatch(r'Volume: (\d+(?:\.\d+)?)( \[MUTED\])?', (output or '').strip())
            self.volume = (round(float(match[1]) * 100), bool(match[2])) if match else None
            self.update_volume()
        self.run(VOLUME, received)

    def run(self, args, receive):
        self.busy = True
        self.update_volume()
        flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE
        try:
            process = Gio.Subprocess.new(args, flags)
        except GLib.Error as exc:
            logging.debug('wpctl unavailable: %s', exc)
            self.busy = False
            receive(None)
            return
        timeout = GLib.timeout_add(2000, lambda: (process.force_exit(), GLib.SOURCE_REMOVE)[1])

        def done(obj, result):
            if GLib.MainContext.default().find_source_by_id(timeout) is not None:
                GLib.source_remove(timeout)
            self.busy = False
            try:
                _, output, _ = obj.communicate_utf8_finish(result)
                reply = output if obj.get_successful() else None
            except GLib.Error:
                reply = None
            receive(reply)
        process.communicate_utf8_async(None, None, done)

    def update_volume(self):
        for button in (self.mute, self.lower, self.raise_):
            button.set_sensitive(not self.busy and self.volume is not None)
        if self.volume is None:
            self.level.set_text('Volume tidak tersedia')
            return
        percent, muted = self.volume
        self.level.set_text(f'Volume {percent}%'+ (' · Bisu' if muted else ''))
        self.mute.get_image().set_from_icon_name('audio-volume-muted-symbolic' if muted else
                                                  'audio-volume-high-symbolic', Gtk.IconSize.BUTTON)

import logging
import re

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Playerctl', '2.0')
from gi.repository import Gio, GLib, Gtk, Pango, Playerctl

from artwork import ArtworkLoader
from media import MediaModel, Playback, PlayerSnapshot, format_clock

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
        self.volume = None
        self.model = MediaModel()
        self.artwork = ArtworkLoader()
        self.art_url = None
        self.active = False
        self.position_source = 0
        self.building_menu = False
        self.seeking = False
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
        self.progress = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.progress.set_draw_value(False)
        self.progress.set_size_request(-1, 14)
        self.progress.get_accessible().set_name('Posisi lagu')
        self.progress.connect('change-value', self.seek)
        self.elapsed = Gtk.Label(label='', xalign=0)
        self.elapsed.get_style_context().add_class('notice-meta')
        self.players = Gtk.MenuButton()
        self.players.set_image(Gtk.Image.new_from_icon_name('view-list-symbolic', Gtk.IconSize.BUTTON))
        self.players.set_tooltip_text('Pilih pemutar')
        self.players.get_accessible().set_name('Pilih pemutar')
        line = Gtk.Box(spacing=4)
        line.pack_start(self.progress, True, True, 0)
        line.pack_start(self.elapsed, False, False, 0)
        line.pack_start(self.players, False, False, 0)
        self.pack_start(line, False, False, 0)
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
        self.manager.connect('player-vanished', self.player_vanished)
        for name in self.manager.props.player_names:
            self.add_player(self.manager, name)
        self.select_player()
        self.update_volume()

    def player_vanished(self, _manager, player):
        self.model.vanish(str(player.props.player_name))
        self.select_player()

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
        snapshots = [self.snapshot(player) for player in self.manager.props.players]
        snapshot = self.model.choose(snapshots)
        names = {str(p.props.player_name): p for p in self.manager.props.players}
        self.player = names.get(snapshot.name) if snapshot else None
        if snapshot:
            self.title.set_text(snapshot.title or snapshot.name)
            self.artist.set_text(snapshot.artist or snapshot.name)
            playing = snapshot.playback is Playback.PLAYING
            self.play.get_image().set_from_icon_name('media-playback-pause-symbolic' if playing else
                                                      'media-playback-start-symbolic', Gtk.IconSize.BUTTON)
            self.play.set_sensitive(snapshot.can_control and (snapshot.can_pause if playing else snapshot.can_play))
            self.previous.set_sensitive(snapshot.can_control and snapshot.can_previous)
            self.next.set_sensitive(snapshot.can_control and snapshot.can_next)
            self.progress.set_sensitive(snapshot.can_seek)
            self.progress.set_range(0, max(1, snapshot.length_us or 1))
            if self.model.track_changed(snapshot):
                self.model.accept(snapshot)
                self.art_url = None
                self.load_art(snapshot.art_url)
            self.update_position(snapshot)
            self.build_player_menu([s.name for s in snapshots])
            if not playing:
                self.stop_position()
        else:
            self.stop_position()
        self.media.set_visible(snapshot is not None)
        self.resized()

    @staticmethod
    def snapshot(player):
        metadata = player.props.metadata
        def text(key):
            value = metadata.lookup_value(key, None) if metadata else None
            kind = value.get_type_string() if value else ''
            if kind == 's':
                return value.get_string()
            if kind == 'as':
                return ', '.join(value.unpack())
            return ''
        def number(key):
            value = metadata.lookup_value(key, GLib.VariantType.new('x')) if metadata else None
            return value.get_int64() if value else None
        status = player.props.playback_status
        playback = (Playback.PLAYING if status == Playerctl.PlaybackStatus.PLAYING else
                    Playback.PAUSED if status == Playerctl.PlaybackStatus.PAUSED else Playback.STOPPED)
        metadata_id = text('mpris:trackid') or text('xesam:url')
        return PlayerSnapshot(
            name=str(player.props.player_name), playback=playback,
            track_id=metadata_id or text('xesam:title'),
            title=text('xesam:title'), artist=text('xesam:artist'), art_url=text('mpris:artUrl') or None,
            length_us=number('mpris:length'), can_control=player.props.can_control,
            can_play=player.props.can_play, can_pause=player.props.can_pause,
            can_next=player.props.can_go_next, can_previous=player.props.can_go_previous,
            can_seek=player.props.can_seek)

    def update_position(self, snapshot):
        if self.seeking:
            return
        position = self.player.get_position() if self.player else -1
        length = snapshot.length_us or 0
        self.progress.set_value(min(position, length) if length and position >= 0 else 0)
        self.elapsed.set_text(f'{format_clock(max(position, 0))} / {format_clock(length) or "--:--"}')
        if snapshot.playback is Playback.PLAYING and self.active:
            if not self.position_source:
                self.position_source = GLib.timeout_add_seconds(1, self.tick_position)
        else:
            self.stop_position()

    def tick_position(self):
        if not self.active or not self.player:
            self.position_source = 0
            return GLib.SOURCE_REMOVE
        self.update_position(self.snapshot(self.player))
        return GLib.SOURCE_CONTINUE if self.position_source else GLib.SOURCE_REMOVE

    def stop_position(self):
        if self.position_source:
            GLib.source_remove(self.position_source)
            self.position_source = 0

    def seek(self, _scale, _scroll, value):
        self.seeking = True
        if self.player and self.player.props.can_seek:
            self.player.set_position(int(value))
        GLib.timeout_add(400, self.seek_settled)
        return False

    def seek_settled(self):
        self.seeking = False
        return GLib.SOURCE_REMOVE

    def build_player_menu(self, names):
        self.building_menu = True
        menu = Gtk.Menu()
        group = []
        self.player_items = []
        for name in sorted(names):
            item = Gtk.RadioMenuItem(label=name, group=group[0] if group else None)
            group.append(item)
            item.player_name = name
            item.connect('activate', self.prefer_player, name)
            item.set_active(name == self.model.selected)
            menu.append(item)
            self.player_items.append(item)
        menu.show_all()
        self.players.set_popup(menu)
        self.players.set_visible(len(names) > 1)
        self.building_menu = False

    def prefer_player(self, _item, name):
        if self.building_menu:
            return
        self.model.prefer(name)
        self.select_player()

    def set_visible(self, visible):
        if visible == self.active:
            super().set_visible(visible)
            return
        super().set_visible(visible)
        self.active = visible
        if visible:
            self.select_player()
            self.load_art(self.art_url)
        else:
            self.stop_position()
            self.artwork.load(None, self.art_ready)

    def load_art(self, url):
        self.art_url = url
        self.cover.set_from_icon_name('audio-x-generic-symbolic', Gtk.IconSize.BUTTON)
        if not url or not self.active:
            return
        self.artwork.load(url, self.art_ready)

    def art_ready(self, url, artwork):
        if artwork is None:
            self.cover.set_from_icon_name('audio-x-generic-symbolic', Gtk.IconSize.BUTTON)
            return
        self.cover.set_from_pixbuf(artwork.scale_simple(34, 34, 2))

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

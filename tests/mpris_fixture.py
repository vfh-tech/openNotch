import os
import sys

from gi.repository import Gio, GLib

SERVICE = sys.argv[1] if len(sys.argv) > 1 else 'org.mpris.MediaPlayer2.NotchProbe'
STATE = os.environ['MPRIS_STATE']
PLAYER = 'org.mpris.MediaPlayer2.Player'
ROOT = 'org.mpris.MediaPlayer2'
PATH = '/org/mpris/MediaPlayer2'


def log(entry):
    with open(STATE, 'a') as handle:
        handle.write(entry + '\n')


def variant(kind, value):
    return GLib.Variant(kind, value)


state = {
    'PlaybackStatus': 'Paused',
    'Metadata': {'xesam:title': 'Lagu Satu', 'xesam:artist': ['Notch Player'],
                 'mpris:trackid': '/track/one', 'mpris:length': GLib.Variant('x', 180_000_000),
                 'mpris:artUrl': os.environ.get('MPRIS_ART', '')},
    'Position': 42_000_000,
}

player_xml = ''.join((
    f'<node><interface name="{PLAYER}">',
    '<method name="Previous"/><method name="PlayPause"/><method name="Next"/>',
    '<method name="Play"/><method name="Pause"/>',
    '<method name="SetPosition"><arg type="o" direction="in"/><arg type="x" direction="in"/></method>',
    '<method name="Seek"><arg type="x" direction="in"/></method>',
    '<property name="PlaybackStatus" type="s" access="read"/>',
    '<property name="Metadata" type="a{sv}" access="read"/>',
    '<property name="Position" type="x" access="read"/>',
    '<property name="CanControl" type="b" access="read"/>',
    '<property name="CanPlay" type="b" access="read"/>',
    '<property name="CanPause" type="b" access="read"/>',
    '<property name="CanGoNext" type="b" access="read"/>',
    '<property name="CanGoPrevious" type="b" access="read"/>',
    '<property name="CanSeek" type="b" access="read"/>',
    '<property name="LoopStatus" type="s" access="read"/>',
    '<property name="Shuffle" type="b" access="read"/>',
    '<property name="Volume" type="d" access="read"/>',
    '<property name="Rate" type="d" access="read"/>',
    '<property name="MinimumRate" type="d" access="read"/>',
    '<property name="MaximumRate" type="d" access="read"/>',
    f'<signal name="Seeked"><arg type="x"/></signal>',
    '</interface>',
    f'<interface name="{ROOT}">',
    '<property name="Identity" type="s" access="read"/>',
    '<property name="DesktopEntry" type="s" access="read"/>',
    '<property name="CanQuit" type="b" access="read"/>',
    '<property name="CanRaise" type="b" access="read"/>',
    '<property name="HasTrackList" type="b" access="read"/>',
    '<property name="SupportedUriSchemes" type="as" access="read"/>',
    '<property name="SupportedMimeTypes" type="as" access="read"/>',
    '</interface></node>'))


def get_property(_conn, _sender, _path, interface, name):
    if interface == ROOT:
        return {'Identity': variant('s', 'Notch Probe'), 'DesktopEntry': variant('s', 'notch'),
                'CanQuit': variant('b', False), 'CanRaise': variant('b', False),
                'HasTrackList': variant('b', False), 'SupportedUriSchemes': variant('as', []),
                'SupportedMimeTypes': variant('as', [])}.get(name)
    if name == 'Metadata':
        return variant('a{sv}', {k: v if isinstance(v, GLib.Variant) else variant(
            'as' if isinstance(v, list) else 's', v) for k, v in state['Metadata'].items()})
    return {
        'PlaybackStatus': variant('s', state['PlaybackStatus']),
        'Position': variant('x', state['Position']),
        'CanControl': variant('b', True), 'CanPlay': variant('b', True),
        'CanPause': variant('b', True), 'CanGoNext': variant('b', True),
        'CanGoPrevious': variant('b', True), 'CanSeek': variant('b', True),
        'LoopStatus': variant('s', 'None'), 'Shuffle': variant('b', False),
        'Volume': variant('d', 1.0), 'Rate': variant('d', 1.0),
        'MinimumRate': variant('d', 1.0), 'MaximumRate': variant('d', 1.0),
    }.get(name)


def call(_conn, _sender, _path, interface, method, parameters, invocation):
    log(method + ' ' + (parameters.print_(True) if parameters is not None else ''))
    if method in ('PlayPause', 'Play', 'Pause'):
        state['PlaybackStatus'] = 'Playing' if state['PlaybackStatus'] != 'Playing' else 'Paused'
    elif method == 'SetPosition':
        state['Position'] = parameters.unpack()[1]
    elif method == 'Seek':
        state['Position'] = max(0, state['Position'] + parameters.unpack()[0])
    invocation.return_value(None)


bus = Gio.bus_get_sync(Gio.BusType.SESSION)
node = Gio.DBusNodeInfo.new_for_xml(player_xml)
for index in (0, 1):
    bus.register_object(PATH, node.interfaces[index], call, get_property, None)
bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'RequestName',
              GLib.Variant('(su)', (SERVICE, 0)), None, Gio.DBusCallFlags.NONE, 1500, None)
log('ready')
GLib.MainLoop().run()

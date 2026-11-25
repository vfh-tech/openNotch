from html.parser import HTMLParser

from gi.repository import Gio, GLib

INTERFACE = 'org.freedesktop.Notifications'
PATH = '/org/freedesktop/Notifications'
RULE = (f"type='method_call',destination='{INTERFACE}',interface='{INTERFACE}',"
        f"path='{PATH}',member='Notify'")


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, _attrs):
        if tag in ('br', 'p'):
            self.parts.append(' ')


def plain_text(text, limit):
    parser = PlainText()
    parser.feed(text[:4096])
    parser.close()
    return ' '.join(''.join(parser.parts).split())[:limit]


class NotificationMonitor:
    def __init__(self, show):
        self.show = show
        self.active = False
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        flags = (Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                 Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION)
        self.connection = Gio.DBusConnection.new_for_address_sync(address, flags, None, None)
        self.connection.set_exit_on_close(False)
        self.connection.add_filter(self.filter)
        self.connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                                  'org.freedesktop.DBus.Monitoring', 'BecomeMonitor',
                                  GLib.Variant('(asu)', ([RULE], 0)), None,
                                  Gio.DBusCallFlags.NONE, 2000, None)
        self.active = True

    def filter(self, _connection, message, incoming):
        if not self.active or not incoming:
            return message
        if (message.get_message_type() == Gio.DBusMessageType.METHOD_CALL and
                message.get_interface() == INTERFACE and message.get_path() == PATH and
                message.get_member() == 'Notify'):
            data = message.get_body()
            if data and data.get_type_string() == '(susssasa{sv}i)':
                app = data.get_child_value(0).get_string()
                title = data.get_child_value(3).get_string()
                body = data.get_child_value(4).get_string()
                GLib.idle_add(self.deliver, app, title, body)
        return None

    def deliver(self, app, title, body):
        self.show(plain_text(app, 48) or 'Aplikasi', plain_text(title, 100), plain_text(body, 180))
        return GLib.SOURCE_REMOVE

import logging
import os

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gio, GLib, Gtk

from shelf import ShelfStore, parse_drop

MAX_ROWS = 4


class ShelfPanel(Gtk.Box):
    def __init__(self, changed, width, store_path):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_size_request(width, -1)
        self.changed = changed
        self.store = ShelfStore(store_path)
        self.title = Gtk.Label(xalign=0)
        self.title.get_style_context().add_class('notice-title')
        self.hint = Gtk.Label(label='Tarik berkas ke sini', xalign=0)
        self.store = ShelfStore(store_path)
        self.store_file = store_path
        self.pack_start(self.title, False, False, 0)
        self.pack_start(self.hint, False, False, 0)
        self.rows = []
        for _ in range(MAX_ROWS):
            row = Gtk.Box(spacing=6)
            label = Gtk.Label(xalign=0)
            label.set_ellipsize(3)
            label.set_single_line_mode(True)
            open_button = Gtk.Button(label='Buka')
            open_button.connect('clicked', self.open_item)
            remove_button = Gtk.Button(label='Hapus')
            remove_button.connect('clicked', self.remove_item)
            row.pack_start(label, True, True, 0)
            row.pack_start(open_button, False, False, 0)
            row.pack_start(remove_button, False, False, 0)
            row.label, row.open_button, row.remove_button = label, open_button, remove_button
            self.rows.append(row)
            self.pack_start(row, False, False, 0)
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.drag_dest_add_text_targets()
        self.connect('drag-data-received', self.received)
        self.render()

    def receive_drop(self, uri_text, files):
        return self.store.add_all(parse_drop(uri_text, files))

    def received(self, _widget, _context, _x, _y, data, _info, _time):
        uris = data.get_uris() or []
        text = data.get_text() if data.get_text() is not None else ''
        files = []
        for uri in uris:
            parsed = Gio.File.new_for_uri(uri)
            path = parsed.get_path()
            if path:
                files.append(path)
        added = self.receive_drop('\n'.join(uris) if uris else text, files)
        logging.info('Shelf received %d item(s)', added)
        self.render()

    def render(self):
        items = self.store.items
        self.title.set_text('Rak berkas' if items else 'Rak berkas kosong')
        self.hint.set_text(f'{len(items)} item tersimpan' if items else 'Tarik berkas ke sini')
        for index, row in enumerate(self.rows):
            if index < len(items):
                item = items[index]
                mark = '' if item.exists else ' (hilang)'
                row.label.set_text(f'{item.label}{mark}')
                row.item = item
                row.show_all()
                row.open_button.set_sensitive(item.exists)
            else:
                row.item = None
                row.hide()
        self.changed()

    @property
    def height(self):
        rows = len([row for row in self.rows if row.get_visible()])
        return 54 + rows * 30

    def open_item(self, button):
        item = button.get_parent().item
        if item is None or not item.exists:
            return
        try:
            if item.kind == 'text':
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(item.value, -1)
            else:
                Gio.AppInfo.launch_default_for_uri(item.value, None)
        except GLib.Error as exc:
            logging.debug('Shelf open failed: %s', exc)

    def remove_item(self, button):
        item = button.get_parent().item
        if item is not None and self.store.remove(item.id):
            self.render()
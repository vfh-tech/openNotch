import logging

from gi.repository import GLib, Gtk

from agenda import AgendaModel
from agenda_source import load


class AgendaPanel(Gtk.Box):
    def __init__(self, changed, width, refresh_seconds=120):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.set_size_request(width, -1)
        self.changed = changed
        self.model = AgendaModel()
        self.title = Gtk.Label(xalign=0)
        self.title.get_style_context().add_class('notice-title')
        self.summary = Gtk.Label(xalign=0)
        self.summary.get_style_context().add_class('notice-meta')
        self.rows = []
        self.pack_start(self.title, False, False, 0)
        self.pack_start(self.summary, False, False, 0)
        for index in range(self.model.limit):
            label = Gtk.Label(xalign=0)
            label.set_single_line_mode(True)
            label.set_ellipsize(3)
            self.rows.append(label)
            self.pack_start(label, False, False, 0)
        self.source = GLib.timeout_add_seconds(refresh_seconds, self.refresh)
        self.refresh()

    def refresh(self):
        self.loading = True
        self._render(None, None)
        GLib.idle_add(self._load)
        return GLib.SOURCE_CONTINUE

    def _load(self):
        try:
            entries = load()
            self._render(entries, None)
        except Exception as exc:
            logging.debug('Agenda refresh failed: %s', exc)
            self._render(None, exc)
        return GLib.SOURCE_REMOVE

    def _render(self, entries, error):
        if error is not None:
            self.title.set_text('Agenda')
            self.summary.set_text('Sumber kalender tidak tersedia')
            for row in self.rows:
                row.set_text('')
                row.hide()
        elif entries is None:
            self.title.set_text('Agenda')
            self.summary.set_text('Memuat agenda...')
        else:
            self.model.replace(entries)
            self.title.set_text('Agenda hari ini')
            self.summary.set_text(self.model.summary)
            for index, row in enumerate(self.rows):
                if index < len(self.model.entries):
                    entry = self.model.entries[index]
                    row.set_text(f'{entry.time_text}  {entry.title}')
                    row.show()
                else:
                    row.set_text('')
                    row.hide()
        self.changed()

    @property
    def height(self):
        return 20 + 18 + 20 * len([row for row in self.rows if row.get_visible()]) + 6

    def stop(self):
        if self.source:
            GLib.source_remove(self.source)
            self.source = 0
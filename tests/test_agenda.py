import unittest
from datetime import datetime

from agenda import AgendaEntry, AgendaModel, Kind, classify


class AgendaModelTests(unittest.TestCase):
    def test_all_day_event_renders_without_a_clock(self):
        entry = AgendaEntry('Rapat', Kind.EVENT, datetime(2026, 11, 25, 0, 0), all_day=True)
        self.assertEqual(entry.time_text, 'Sepanjang hari')

    def test_timed_event_shows_start_time(self):
        entry = AgendaEntry('Rapat', Kind.EVENT, datetime(2026, 11, 25, 9, 5))
        self.assertEqual(entry.time_text, '09:05')

    def test_task_shows_open_state(self):
        entry = AgendaEntry('Kirim laporan', Kind.TASK, datetime(2026, 11, 25, 17, 0))
        self.assertFalse(entry.done)
        self.assertEqual(entry.time_text, '17:00')

    def test_model_sorts_by_start_and_keeps_tasks_after_events(self):
        model = AgendaModel()
        model.replace([
            AgendaEntry('Tugas', Kind.TASK, datetime(2026, 11, 25, 9, 0)),
            AgendaEntry('Siang', Kind.EVENT, datetime(2026, 11, 25, 13, 0)),
            AgendaEntry('Pagi', Kind.EVENT, datetime(2026, 11, 25, 8, 0)),
        ])
        self.assertEqual([e.title for e in model.entries], ['Pagi', 'Siang', 'Tugas'])

    def test_model_caps_the_visible_list(self):
        model = AgendaModel(limit=2)
        model.replace([AgendaEntry(str(i), Kind.EVENT, datetime(2026, 11, 25, i, 0)) for i in range(6)])
        self.assertEqual(len(model.entries), 2)
        self.assertEqual(model.summary, '2 dari 6 agenda')

    def test_empty_model_reports_no_source_content(self):
        model = AgendaModel()
        model.replace([])
        self.assertEqual(model.entries, [])
        self.assertEqual(model.summary, 'Tidak ada agenda hari ini')

    def test_classify_maps_component_kind(self):
        self.assertIs(classify('VEVENT'), Kind.EVENT)
        self.assertIs(classify('VTODO'), Kind.TASK)
        self.assertIsNone(classify('VJOURNAL'))

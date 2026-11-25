import json
import os
import tempfile
import unittest
from pathlib import Path

from settings import DEFAULTS, NotchSettings, clamp


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name, 'notch.json')

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_are_complete(self):
        s = NotchSettings(self.path)
        for key in ('width', 'hover_delay_ms', 'agenda_limit', 'shelf_limit', 'show_agenda', 'show_shelf'):
            self.assertIn(key, s.values)
        self.assertEqual(s.values['width'], DEFAULTS['width'])

    def test_clamps_out_of_range_values(self):
        self.assertEqual(clamp('width', 50), 280)
        self.assertEqual(clamp('width', 5000), 640)
        self.assertEqual(clamp('width', 400), 400)

    def test_rejects_wrong_types(self):
        self.assertEqual(clamp('width', 'wide'), DEFAULTS['width'])
        self.assertEqual(clamp('hover_delay_ms', None), DEFAULTS['hover_delay_ms'])

    def test_clamps_booleans_to_default_when_not_bool(self):
        self.assertEqual(clamp('show_agenda', 'yes'), DEFAULTS['show_agenda'])

    def test_unknown_keys_are_ignored(self):
        self.assertIsNone(clamp('nonexistent', 1))

    def test_persists_only_known_keys(self):
        s = NotchSettings(self.path)
        s.set('width', 420)
        data = json.loads(self.path.read_text())
        self.assertEqual(data['values']['width'], 420)
        self.assertNotIn('bogus', data['values'])

    def test_reload_reads_saved_values(self):
        s = NotchSettings(self.path)
        s.set('show_shelf', False)
        self.assertFalse(NotchSettings(self.path).values['show_shelf'])

    def test_corrupt_file_falls_back_to_defaults(self):
        self.path.write_text('not json')
        self.assertEqual(NotchSettings(self.path).values, DEFAULTS)

    def test_set_returns_the_stored_value(self):
        self.assertEqual(NotchSettings(self.path).set('width', 9999), 640)


class DropGeometryTests(unittest.TestCase):
    def test_panel_is_centered_within_edge_width(self):
        from geometry import panel_rect
        rect = panel_rect(1920, 400, 0)
        self.assertEqual(rect[0], (1920 - 400) // 2)
        self.assertEqual(rect[2], 400)

    def test_negative_margin_is_clamped(self):
        from geometry import panel_rect
        self.assertEqual(panel_rect(1920, 400, -20)[1], 0)

    def test_oversized_panel_is_capped_to_scaled_width(self):
        from geometry import panel_rect
        x, _, w, _ = panel_rect(1280, 3000, 4)
        self.assertEqual(w, 1280)
        self.assertEqual(x, 0)

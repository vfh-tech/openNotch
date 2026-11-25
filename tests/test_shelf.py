import json
import tempfile
import unittest
from pathlib import Path

from shelf import ShelfItem, ShelfStore, parse_drop


class ShelfModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name, 'shelf.json')
        self.store = ShelfStore(self.path, limit=3)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_deduplicates_identical_entries(self):
        item = ShelfItem('file', 'file:///tmp/a.txt', 'a.txt')
        self.store.add(item)
        self.store.add(item)
        self.assertEqual(len(self.store.items), 1)

    def test_limit_evicts_the_oldest_entry(self):
        for name in ('a', 'b', 'c', 'd'):
            self.store.add(ShelfItem('file', f'file:///tmp/{name}', name))
        self.assertEqual([i.label for i in self.store.items], ['b', 'c', 'd'])

    def test_remove_only_drops_the_reference(self):
        source = Path(self.tmp.name, 'keep.txt')
        source.write_text('hello')
        self.store.add(ShelfItem('file', source.as_uri(), 'keep.txt'))
        self.store.remove(self.store.items[0].id)
        self.assertTrue(source.exists())
        self.assertEqual(self.store.items, [])

    def test_persists_and_reloads(self):
        self.store.add(ShelfItem('text', 'catatan', 'Teks'))
        reloaded = ShelfStore(self.path, limit=3)
        self.assertEqual([(i.kind, i.value, i.label) for i in reloaded.items],
                         [('text', 'catatan', 'Teks')])

    def test_corrupt_file_does_not_crash(self):
        self.path.write_text('{not json')
        self.assertEqual(ShelfStore(self.path, limit=3).items, [])

    def test_missing_target_is_flagged_not_dropped(self):
        self.store.add(ShelfItem('file', 'file:///tmp/never-exists', 'ghost'))
        self.assertFalse(self.store.items[0].exists)

    def test_parse_drop_reads_uri_list_and_plain_text(self):
        items = parse_drop('file:///tmp/a.txt\nfile:///tmp/b.txt', None, limit=8)
        self.assertEqual([i.value for i in items], ['file:///tmp/a.txt', 'file:///tmp/b.txt'])
        text = parse_drop('halo dunia', None, limit=8)
        self.assertEqual(text[0].kind, 'text')
        self.assertEqual(text[0].value, 'halo dunia')

    def test_parse_drop_rejects_oversized_text(self):
        self.assertEqual(parse_drop('x' * 5000, None, limit=8), [])

    def test_saved_json_is_valid_after_each_write(self):
        self.store.add(ShelfItem('file', 'file:///tmp/a', 'a'))
        data = json.loads(self.path.read_text())
        self.assertEqual(data['version'], 1)

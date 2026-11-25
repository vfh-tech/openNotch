import unittest

from artwork import ArtworkLoader
from media import MediaModel, PlayerSnapshot, Playback, format_clock


def player(name, status=Playback.PAUSED, track_id='t1', **kw):
    return PlayerSnapshot(name=name, playback=status, track_id=track_id, **kw)


class MediaModelTests(unittest.TestCase):
    def test_prefers_playing_player_when_none_selected(self):
        model = MediaModel()
        chosen = model.choose([player('a'), player('b', Playback.PLAYING)])
        self.assertEqual(chosen.name, 'b')

    def test_selected_player_stays_selected_while_paused(self):
        model = MediaModel()
        self.assertEqual(model.choose([player('a', Playback.PLAYING), player('b')]).name, 'a')
        model.choose([player('a', Playback.PAUSED), player('b', Playback.PLAYING)])
        self.assertEqual(model.selected, 'a')

    def test_live_playing_player_takes_over_from_a_stale_pin(self):
        model = MediaModel()
        model.choose([player('a', Playback.PLAYING)])
        self.assertEqual(model.selected, 'a')
        chosen = model.choose([player('a', Playback.STOPPED), player('b', Playback.PLAYING)])
        self.assertEqual(chosen.name, 'b')
        self.assertEqual(model.selected, 'b')

    def test_vanish_releases_the_pin(self):
        model = MediaModel()
        model.choose([player('a'), player('b', Playback.PLAYING)])
        model.vanish('b')
        chosen = model.choose([player('a')])
        self.assertEqual(chosen.name, 'a')
        self.assertEqual(model.selected, 'a')

    def test_manual_preference_survives_new_playing_player(self):
        model = MediaModel()
        model.choose([player('a')])
        model.prefer('b')
        chosen = model.choose([player('a', Playback.PLAYING), player('b')])
        self.assertEqual(chosen.name, 'b')

    def test_track_rollover_detects_new_track_id(self):
        model = MediaModel()
        first = model.choose([player('a', track_id='one')])
        self.assertTrue(model.track_changed(first))
        model.accept(first)
        self.assertFalse(model.track_changed(player('a', track_id='one')))
        self.assertTrue(model.track_changed(player('a', track_id='two')))

    def test_clock_format_handles_unknown_length(self):
        self.assertEqual(format_clock(65_000_000), '1:05')
        self.assertEqual(format_clock(None), '')


class FakeFetch:
    def __init__(self):
        self.calls = []

    def __call__(self, url, done):
        self.calls.append((url, done))


class ArtworkLoaderTests(unittest.TestCase):
    def setUp(self):
        self.fetch = FakeFetch()
        self.events = []
        self.loader = ArtworkLoader(self.fetch, decode=lambda data: data)

    def load(self, url):
        self.loader.load(url, lambda url, art: self.events.append((url, art)))

    def test_drops_stale_callback_after_a_new_request(self):
        self.load('file:///a.png')
        self.load('file:///b.png')
        self.fetch.calls[0][1](b'old')
        self.assertEqual(self.events, [])
        self.fetch.calls[1][1](b'new')
        self.assertEqual(self.events, [('file:///b.png', b'new')])

    def test_cancelling_invalidates_pending_request(self):
        self.load('file:///a.png')
        self.load(None)
        self.fetch.calls[0][1](b'late')
        self.assertEqual(self.events, [])

    def test_decode_failure_reports_no_artwork(self):
        self.load('file:///bad.png')
        self.loader.decode = lambda data: (_ for _ in ()).throw(ValueError('bad'))
        self.fetch.calls[-1][1](b'x')
        self.assertEqual(self.events, [('file:///bad.png', None)])

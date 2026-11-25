from pathlib import Path
from urllib.parse import unquote, urlsplit
import gi


gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Soup', '3.0')
from gi.repository import GdkPixbuf, Gio, GLib, Soup

MAX_BYTES = 6 * 1024 * 1024
TIMEOUT_SECONDS = 8


def decode_pixbuf(data):
    return GdkPixbuf.Pixbuf.new_from_stream(
        Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data)), None)


def fetch_bytes(url, done):
    parsed = urlsplit(url)
    if parsed.scheme == 'file':
        path = Path(unquote(parsed.path))
        try:
            if path.stat().st_size > MAX_BYTES:
                raise ValueError('Artwork is too large')
            done(path.read_bytes())
        except OSError as exc:
            print(f'artwork: {exc}')
            done(None)
        return
    if parsed.scheme not in ('http', 'https'):
        done(None)
        return
    session = Soup.Session()
    session.set_timeout(TIMEOUT_SECONDS)
    message = Soup.Message.new('GET', url)

    def finished(source, result, _data=None):
        try:
            payload = source.send_and_read_finish(result)
            data = payload.get_data()
            done(data if data and len(data) <= MAX_BYTES else None)
        except GLib.Error:
            done(None)
    session.send_and_read_async(message, GLib.PRIORITY_DEFAULT, None, finished)


class ArtworkLoader:
    def __init__(self, fetch=fetch_bytes, decode=decode_pixbuf):
        self.fetch = fetch
        self.decode = decode
        self.generation = 0

    def load(self, url, done):
        self.generation += 1
        generation = self.generation
        if not url:
            return

        def finish(data):
            if generation != self.generation:
                return
            artwork = None
            if data:
                try:
                    artwork = self.decode(data)
                except Exception:
                    artwork = None
            done(url, artwork)
        self.fetch(url, finish)
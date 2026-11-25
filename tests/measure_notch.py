import argparse
import json
import math
import os
import time
from pathlib import Path
from types import SimpleNamespace

from notch import Gdk, GLib, Gtk, Notch


def process_ticks():
    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    return int(fields[11]) + int(fields[12])


def rss_kib():
    for line in Path('/proc/self/smaps_rollup').read_text().splitlines():
        if line.startswith('Rss:'):
            return int(line.split()[1])
    raise RuntimeError('No process RSS')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--idle-seconds', type=int, default=60)
    parser.add_argument('--transitions', type=int, default=20)
    args = parser.parse_args()
    notch = Notch()
    event = SimpleNamespace(detail=Gdk.NotifyType.NONLINEAR)
    start = time.monotonic()
    ticks = process_ticks()
    latency = []
    error = None

    def begin_idle():
        nonlocal start, ticks, error
        if not notch.window.get_mapped():
            error = 'Notch did not map'
            Gtk.main_quit()
            return GLib.SOURCE_REMOVE
        start, ticks = time.monotonic(), process_ticks()
        GLib.timeout_add_seconds(args.idle_seconds, begin_transitions)
        return GLib.SOURCE_REMOVE

    def begin_transitions():
        elapsed = time.monotonic() - start
        result.update(idle_pct_one_cpu=100 * (process_ticks() - ticks) / (elapsed * os.sysconf('SC_CLK_TCK')),
                      rss_kib=rss_kib())
        transition()
        return GLib.SOURCE_REMOVE

    def transition():
        entered = time.monotonic()
        notch.enter(None, event)

        def observe(_widget, _clock):
            nonlocal error
            elapsed = time.monotonic() - entered
            if not notch.grid.get_mapped():
                if elapsed > 2:
                    error = 'Tray did not become visible after hover'
                    Gtk.main_quit()
                    return False
                return True
            latency.append(1000 * elapsed)
            notch.leave(None, event)
            if len(latency) == args.transitions:
                Gtk.main_quit()
            else:
                GLib.timeout_add(650, transition)
            return False

        notch.window.add_tick_callback(observe)
        return GLib.SOURCE_REMOVE

    result = {}
    GLib.timeout_add(800, begin_idle)
    Gtk.main()
    assert error is None and len(latency) == args.transitions, (error, len(latency))
    result['hover_visible_p95_ms'] = sorted(latency)[math.ceil(.95 * len(latency)) - 1]
    result['transitions'] = len(latency)
    print(json.dumps(result))


if __name__ == '__main__':
    main()

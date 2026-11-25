# openNotch

A macOS-style notch for COSMIC and other Wayland desktops. A pill sits at the top centre of the screen, expands on hover, and shows a focus timer, the current track, today's agenda, and desktop notifications.

## Features

**Focus timer**

- Duration is editable from 1 to 180 minutes with a spin button.
- Start, pause, resume, and reset.
- A green dot blinks while a session runs, in the open row and in the collapsed pill.
- When time is up the notch flashes green, plays `alarm-clock-elapsed.oga`, shows a banner, and cuts both the sound and the banner at 3 seconds.
- The timer keeps running while the notch is collapsed.

**Music**

- Reads any MPRIS player through Playerctl.
- Shows title, artist, and artwork. Artwork is fetched from `file://` or `http(s)://` with a 6 MiB cap and an 8 second timeout.
- Play, pause, previous, next, and seek when the player reports a length.
- A player picker appears when several players are registered.
- A playing player is chosen automatically. A manual choice sticks until that player disappears.

**Agenda**

- Reads selected Evolution calendars and task lists through ECal and EDataServer.
- Lists today's events first, then open tasks, capped at 4 entries.
- Refreshes every two minutes without blocking the GTK thread.

**Notifications**

- Displays desktop notifications in the notch instead of a separate banner.
- Notifications take priority over the timer row and dismiss on click.

**Interaction**

- Hover expands the notch, leave collapses it after 300 ms.
- Scroll cycles between `all`, `media`, and `agenda`.
- Escape collapses, Return or Space opens.
- The notch re-binds itself when the display is disconnected and reconnected.

## Requirements

- Wayland with `zwlr_layer_shell_v1`. X11 does not work.
- Python 3.10 or newer with PyGObject
- GTK 3 and GDK 3
- `gtk-layer-shell` typelib
- `playerctl` for music and volume
- `wpctl` from WirePlumber for volume
- Evolution Data Server with `ECal`, `EDataServer`, and `ICalGLib` typelibs for the agenda
- libsoup 3 for artwork over HTTP
- `paplay` for the alert sound
- systemd user session for autostart and restart

Optional typelibs are bundled in `runtime/`, which `launch.sh` puts on `GI_TYPELIB_PATH` and `LD_LIBRARY_PATH`. That directory is gitignored because it holds vendor data.

## Install

```sh
git clone git@github.com:vfh-tech/openNotch.git
cd openNotch
mkdir -p ~/.local/share/openNotch
cp -r ./* ~/.local/share/openNotch/
install -Dm644 cosmic-tray-notch.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cosmic-tray-notch.service
```

The service unit hardcodes its `ExecStart` path. Edit it if the checkout lives elsewhere.

`launch.sh` exits unless `XDG_CURRENT_DESKTOP` contains `COSMIC`. Delete that `case` block to try another compositor.

### Enabling notification routing

The notch watches `org.freedesktop.Notifications` with a D-Bus monitor, so every app notification also reaches the notch. To stop COSMIC from drawing a second banner, turn on Do Not Disturb:

```sh
mkdir -p ~/.config/cosmic/com.system76.CosmicNotifications/v1
printf 'true' > ~/.config/cosmic/com.system76.CosmicNotifications/v1/do_not_disturb
```

## Tests

```sh
python3 -m unittest discover -s tests
```

32 unit tests cover settings clamping, media selection, agenda ordering, and notch state precedence. They need no display.

Live probes drive a real Wayland session and are not part of the suite:

| Probe | What it does |
|---|---|
| `tests/live_notch.py` | Hover, notification priority, banner dismissal, monitor disconnect and reconnect |
| `tests/live_media.py` | Two MPRIS test players, artwork, seek, player switch |
| `tests/measure_notch.py` | Idle CPU, RSS, and hover latency |
| `tests/mpris_fixture.py` | Scriptable MPRIS player used by the probes |

## Configuration

Settings are read from `~/.config/cosmic-tray-notch/notch.json`. Values outside range are clamped to the nearest bound, unknown keys are ignored, and a corrupt file falls back to defaults.

| Key | Default | Range | Applied |
|---|---|---|---|
| `width` | 368 | 280 to 640 | not yet |
| `hover_delay_ms` | 100 | 0 to 800 | not yet |
| `agenda_limit` | 4 | 0 to 8 | not yet |
| `show_agenda` | true | boolean | yes |
| `show_media` | true | boolean | yes |
| `scroll_navigation` | true | boolean | yes |

The first three are validated and stored but the notch still uses a fixed 368 px width, a 300 ms close delay, and 4 agenda rows. Wiring them is open work.

## Project layout

| File | Responsibility |
|---|---|
| `notch.py` | Window, drawing, layout, hover, animation |
| `notch_state.py` | Which page is showing and why |
| `focus_timer.py` | Timer state, spin button, blinking dot |
| `audio.py` | Music and volume controls |
| `media.py` | Player selection rules |
| `artwork.py` | Bounded artwork loading with stale-callback rejection |
| `agenda.py` | Agenda ordering and formatting |
| `agenda_source.py` | ECal reader |
| `agenda_panel.py` | Agenda widget |
| `notifications.py` | Filtered D-Bus notification monitor |
| `outputs.py` | Wayland output binding and recovery |
| `geometry.py` | Panel geometry and section cycling |
| `settings.py` | Validated settings store |

## Status

Verified on Pop!_OS 24.04 with COSMIC 1.11 on one 1920x1080 HDMI display. The notch paints 368 px wide and centres at 0 px offset, measured from screenshots.

Not verified:

- Physical HDMI unplug and replug. The recovery path is exercised only through a simulated display list.
- The alert sound reaching the speakers. The 3 second cutoff is measured from the banner, not from audio.
- Any display server other than COSMIC.
- Multi-monitor layouts.

Features were deliberately dropped because this machine has no such hardware: battery, backlight, and camera mirror. A file shelf existed and was removed because it reserved 178 px while empty.

## License

MIT. See [LICENSE](LICENSE).

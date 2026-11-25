# openNotch

A macOS-style notch for COSMIC and other Wayland desktops. It shows a focus timer, the current track, today's agenda, and desktop notifications in a panel that expands on hover.

## What it does

- **Focus timer.** Editable 1 to 180 minutes, pause and resume, a green dot that blinks while a session runs, and a colour flash with an alarm sound when the time is up.
- **Music.** Reads any MPRIS player, shows title, artist and artwork, with play, pause, skip, seek, and a player picker when several are active.
- **Agenda.** Reads selected Evolution calendars and task lists through ECal and lists the next entries for today.
- **Notifications.** Displays desktop notifications in the notch instead of a separate banner.
- **Hover interaction.** The notch expands on hover, collapses when the pointer leaves, and recovers when a monitor is disconnected and reconnected.

## Requirements

- Wayland with the `zwlr_layer_shell_v1` protocol
- Python 3.10 or newer with PyGObject
- GTK 3 with `gtk-layer-shell`
- `playerctl` for music
- `wpctl` (WirePlumber) for volume
- Evolution Data Server with `ECal` and `EDataServer` typelibs for the agenda
- libsoup 3 for artwork fetched over HTTP

Bundled typelibs live in `runtime/`. They include GtkLayerShell, Playerctl, ECal, EDataServer, and their dependencies.

## Install

```sh
mkdir -p ~/.local/share/cosmic-tray-notch
cp -r ./* ~/.local/share/cosmic-tray-notch/
install -Dm644 cosmic-tray-notch.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cosmic-tray-notch.service
```

`launch.sh` exits unless `XDG_CURRENT_DESKTOP` contains `COSMIC`. Remove that check to try another Wayland compositor.

## Tests

```sh
python3 -m unittest discover -s tests
```

`tests/live_notch.py` and `tests/live_media.py` drive a real Wayland session. `tests/mpris_fixture.py` provides scriptable MPRIS players for those probes.

## Configuration

Settings live in `~/.config/cosmic-tray-notch/notch.json`. The loader clamps out-of-range values and ignores unknown keys.

## Status

Verified on Pop!_OS 24.04 with COSMIC 1.11. The notch paints a 368 px wide pill centred on a 1920 px display. Battery, backlight, and camera features were dropped because this machine has none of that hardware.

## License

MIT. See [LICENSE](LICENSE).

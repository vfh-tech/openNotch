#!/bin/sh
set -eu
case ":${XDG_CURRENT_DESKTOP:-}:" in
    *:COSMIC:*) ;;
    *) exit 0 ;;
esac
if [ "${1:-}" = --autostart ]; then
    exec systemctl --user start cosmic-tray-notch.service
fi
base=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
lib="$base/runtime/usr/lib/x86_64-linux-gnu"
export GDK_BACKEND=wayland
export LD_LIBRARY_PATH="$lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export GI_TYPELIB_PATH="$lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
exec /usr/bin/python3 "$base/notch.py"

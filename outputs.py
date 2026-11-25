from gi.repository import GLib, GtkLayerShell as Layer


class OutputBinding:
    def __init__(self, display, window, refresh):
        self.display = display
        self.window = window
        self.refresh = refresh
        self.monitor = None
        self.pending = 0
        display.connect('monitor-added', self.schedule)
        display.connect('monitor-removed', self.schedule)
        window.connect('delete-event', self.surface_closed)
        self.schedule()

    def surface_closed(self, window, _event):
        window.hide()
        self.monitor = None
        self.refresh(False)
        self.schedule()
        return True

    def schedule(self, *_):
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(150, self.reconcile)

    def reconcile(self):
        self.pending = 0
        monitors = [monitor for i in range(self.display.get_n_monitors())
                    if (monitor := self.display.get_monitor(i)) is not None]
        if self.monitor in monitors and self.window.get_mapped():
            return GLib.SOURCE_REMOVE
        monitor = self.display.get_primary_monitor()
        if monitor not in monitors:
            monitor = monitors[0] if monitors else None
        self.window.hide()
        if self.window.get_realized():
            self.window.unrealize()
        self.monitor = monitor
        if monitor is not None:
            Layer.set_monitor(self.window, monitor)
            self.window.show_all()
        self.refresh(monitor is not None)
        return GLib.SOURCE_REMOVE

"""Main application coordinator for winclip using GTK 3."""
import os
import signal
import sys
import time
from typing import Optional

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from .storage import ClipboardStorage
from .copier import ClipboardCopier
from .monitor import ClipboardMonitor
from .ipc import IPCServer
from .ui import ClipboardWindow


class WinClipApplication:
    def __init__(self, start_visible: bool = False):
        self.start_visible = start_visible
        self.storage = ClipboardStorage()
        self.copier = ClipboardCopier(on_copied_callback=self._on_item_copied_by_app)
        self.monitor = ClipboardMonitor(
            storage=self.storage,
            on_change_callback=self._on_clipboard_changed
        )
        self.ipc_server = IPCServer(command_handler=self._handle_ipc_command)
        self.ui = ClipboardWindow(
            storage=self.storage,
            copier=self.copier
        )
        self._last_toggle_time = 0.0

    def _on_item_copied_by_app(self, content_hash: str):
        """Notify monitor to ignore this copy because it was initiated by our own UI."""
        self.monitor.register_ignore_hash(content_hash)

    def _on_clipboard_changed(self):
        """Called by monitor thread when new clipboard content is detected."""
        if self.ui and self.ui.is_present:
            GLib.idle_add(self.ui.refresh)

    def _handle_ipc_command(self, cmd: str) -> str:
        cmd = cmd.strip().upper()
        if cmd == "PING":
            return "PONG"
        elif cmd == "TOGGLE":
            now = time.time()
            if now - self._last_toggle_time < 0.35:
                return "DEBOUNCED"
            self._last_toggle_time = now
            GLib.idle_add(self.ui.toggle)
            return "OK"
        elif cmd == "SHOW":
            GLib.idle_add(self.ui.show)
            return "OK"
        elif cmd == "HIDE":
            GLib.idle_add(self.ui.hide)
            return "OK"
        elif cmd == "RELOAD":
            GLib.idle_add(self.ui.refresh)
            return "OK"
        elif cmd == "CLEAR":
            self.storage.clear_unpinned()
            GLib.idle_add(self.ui.refresh)
            return "OK"
        elif cmd == "QUIT":
            self.stop()
            GLib.idle_add(Gtk.main_quit)
            return "OK"
        return "UNKNOWN_COMMAND"

    def start(self):
        self.monitor.start()
        self.ipc_server.start()
        if self.start_visible:
            self.ui.show()

    def stop(self):
        self.monitor.stop()
        self.ipc_server.stop()

    def run(self):
        # Graceful signal handling
        signal.signal(signal.SIGINT, lambda s, f: GLib.idle_add(self._shutdown))
        signal.signal(signal.SIGTERM, lambda s, f: GLib.idle_add(self._shutdown))

        self.start()
        try:
            Gtk.main()
        except KeyboardInterrupt:
            self._shutdown()
        return 0

    def _shutdown(self):
        self.stop()
        Gtk.main_quit()

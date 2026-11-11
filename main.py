#!/usr/bin/env python3
"""Windows Clipboard for Ubuntu - Main Entrypoint & CLI."""
import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from winclip.ipc import send_ipc_command, ensure_daemon_running
from winclip.app import WinClipApplication


def main():
    parser = argparse.ArgumentParser(
        description="Windows 11-style Clipboard Manager for Ubuntu (Super+V)"
    )
    parser.add_argument(
        "--toggle",
        action="store_true",
        help="Toggle clipboard popup window (Default for Super+V shortcut)"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show clipboard popup window"
    )
    parser.add_argument(
        "--hide",
        action="store_true",
        help="Hide clipboard popup window"
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run clipboard daemon in background (autostart mode)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear unpinned clipboard items"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check if clipboard daemon is currently running"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop the running clipboard daemon"
    )

    args = parser.parse_args()

    # 1. Status check
    if args.status:
        resp = send_ipc_command("PING")
        if resp == "PONG":
            print("winclip daemon is RUNNING.")
            sys.exit(0)
        else:
            print("winclip daemon is NOT running.")
            sys.exit(1)

    # 2. Stop daemon
    if args.stop:
        resp = send_ipc_command("QUIT")
        if resp == "OK":
            print("winclip daemon stopped successfully.")
            sys.exit(0)
        else:
            print("winclip daemon was not running.")
            sys.exit(0)

    # 3. Clear unpinned history
    if args.clear:
        resp = send_ipc_command("CLEAR")
        if resp == "OK":
            print("Cleared unpinned clipboard items.")
            sys.exit(0)
        else:
            # If daemon not running, clear directly from DB
            from winclip.storage import ClipboardStorage
            storage = ClipboardStorage()
            count = storage.clear_unpinned()
            print(f"Cleared {count} unpinned items from database.")
            sys.exit(0)

    # 4. Hide window
    if args.hide:
        send_ipc_command("HIDE")
        sys.exit(0)

    # 5. Toggle or Show (used by Super+V)
    if args.toggle or args.show or (not args.daemon and len(sys.argv) == 1):
        target_cmd = "SHOW" if args.show else "TOGGLE"
        resp = send_ipc_command(target_cmd)
        if resp in ("OK", "DEBOUNCED"):
            sys.exit(0)

        # Daemon not running yet! Launch daemon in background and show window
        self_script = str(PROJECT_DIR / "main.py")
        started = ensure_daemon_running(self_script)
        if started:
            send_ipc_command("SHOW")
            sys.exit(0)
        else:
            # Fallback: run directly in foreground with window visible
            app = WinClipApplication(start_visible=True)
            sys.exit(app.run())

    # 6. Run daemon mode
    if args.daemon:
        app = WinClipApplication(start_visible=False)
        sys.exit(app.run())


if __name__ == "__main__":
    main()

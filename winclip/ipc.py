"""IPC communication between CLI / shortcut and the running clipboard daemon."""
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .config import SOCKET_PATH


class IPCServer:
    def __init__(self, command_handler: Callable[[str], str]):
        self.command_handler = command_handler
        self.sock_path = str(SOCKET_PATH)
        self._server_sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start listening on the Unix domain socket in a background thread."""
        if os.path.exists(self.sock_path):
            try:
                # Test if another instance is alive
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.settimeout(0.5)
                test_sock.connect(self.sock_path)
                test_sock.close()
                print(f"winclip is already running on {self.sock_path}", file=sys.stderr)
                sys.exit(0)
            except (ConnectionRefusedError, FileNotFoundError, socket.timeout):
                # Stale socket file
                try:
                    os.unlink(self.sock_path)
                except OSError:
                    pass

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self.sock_path)
        self._server_sock.listen(5)
        self._running = True

        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="IPCServer")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        if os.path.exists(self.sock_path):
            try:
                os.unlink(self.sock_path)
            except OSError:
                pass

    def _listen_loop(self):
        while self._running:
            try:
                conn, _ = self._server_sock.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except Exception:
                break

    def _handle_client(self, conn: socket.socket):
        with conn:
            try:
                conn.settimeout(2.0)
                data = conn.recv(1024).decode("utf-8").strip()
                if not data:
                    return
                resp = self.command_handler(data)
                conn.sendall(f"{resp}\n".encode("utf-8"))
            except Exception:
                pass


def send_ipc_command(cmd: str, timeout: float = 1.0) -> Optional[str]:
    """
    Send a command to the running daemon.
    Returns the response string, or None if daemon is not running.
    """
    sock_path = str(SOCKET_PATH)
    if not os.path.exists(sock_path):
        return None

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall(f"{cmd}\n".encode("utf-8"))
        resp = s.recv(1024).decode("utf-8").strip()
        s.close()
        return resp
    except Exception:
        return None


def ensure_daemon_running(entrypoint_script: str) -> bool:
    """Check if daemon is responding, if not, launch it in background."""
    resp = send_ipc_command("PING", timeout=0.3)
    if resp == "PONG":
        return True

    # Spawn daemon in detached mode
    subprocess.Popen(
        [sys.executable, entrypoint_script, "--daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True
    )

    # Wait up to 3 seconds for socket to become available
    start = time.time()
    while time.time() - start < 3.0:
        time.sleep(0.1)
        resp = send_ipc_command("PING", timeout=0.2)
        if resp == "PONG":
            return True

    return False

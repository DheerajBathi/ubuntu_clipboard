"""Clipboard writer: copies text and images back to the system clipboard."""
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Callable

IS_WAYLAND = os.environ.get("XDG_SESSION_TYPE") == "wayland"
HAS_WL_COPY = shutil.which("wl-copy") is not None
HAS_XCLIP = shutil.which("xclip") is not None


class ClipboardCopier:
    def __init__(self, on_copied_callback: Optional[Callable[[str], None]] = None):
        """
        :param on_copied_callback: Callback receiving the content_hash of the copied item
                                   so the monitor can ignore the resulting change event.
        """
        self.on_copied_callback = on_copied_callback

    def copy_text(self, text: str, content_hash: Optional[str] = None) -> bool:
        """Copy plain text to system clipboard."""
        if content_hash and self.on_copied_callback:
            self.on_copied_callback(content_hash)

        data = text.encode("utf-8")
        success = False

        if HAS_WL_COPY:
            try:
                proc = subprocess.Popen(["wl-copy", "--"], stdin=subprocess.PIPE)
                proc.communicate(input=data, timeout=2.0)
                if proc.returncode == 0:
                    success = True
            except Exception:
                pass

        if HAS_XCLIP and (not IS_WAYLAND or not success):
            try:
                proc = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE
                )
                proc.communicate(input=data, timeout=2.0)
                if proc.returncode == 0:
                    success = True
            except Exception:
                pass

        return success

    def copy_image(self, image_path: str, content_hash: Optional[str] = None) -> bool:
        """Copy an image file to system clipboard as image/png."""
        if not os.path.exists(image_path):
            return False

        if content_hash and self.on_copied_callback:
            self.on_copied_callback(content_hash)

        try:
            with open(image_path, "rb") as f:
                img_data = f.read()
        except OSError:
            return False

        success = False

        if HAS_WL_COPY:
            try:
                proc = subprocess.Popen(["wl-copy", "-t", "image/png"], stdin=subprocess.PIPE)
                proc.communicate(input=img_data, timeout=3.0)
                if proc.returncode == 0:
                    success = True
            except Exception:
                pass

        if HAS_XCLIP and (not IS_WAYLAND or not success):
            try:
                proc = subprocess.Popen(
                    ["xclip", "-selection", "clipboard", "-t", "image/png"],
                    stdin=subprocess.PIPE
                )
                proc.communicate(input=img_data, timeout=3.0)
                if proc.returncode == 0:
                    success = True
            except Exception:
                pass

        return success

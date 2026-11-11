"""Background clipboard watcher for Ubuntu without screen blinking."""
import hashlib
import io
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Callable, Set

from PIL import Image

from .config import (
    IMAGES_DIR,
    THUMBS_DIR,
    POLL_INTERVAL_SECONDS,
    THUMBNAIL_MAX_SIZE,
)
from .storage import ClipboardStorage

HAS_XCLIP = shutil.which("xclip") is not None

# Preferred targets for images
IMAGE_TARGETS = {
    "image/png",
    "image/jpeg",
    "image/bmp",
    "image/webp",
    "image/tiff",
}

# Preferred targets for text
TEXT_TARGETS = {
    "UTF8_STRING",
    "text/plain;charset=utf-8",
    "text/plain",
    "STRING",
    "TEXT",
}


def human_readable_size(size_bytes: int) -> str:
    """Format bytes into readable string like '45 KB' or '1.2 MB'."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


class ClipboardMonitor:
    def __init__(
        self,
        storage: ClipboardStorage,
        on_change_callback: Optional[Callable[[], None]] = None
    ):
        self.storage = storage
        self.on_change_callback = on_change_callback
        self.last_hash = self.storage.get_latest_hash()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ignored_hashes: Set[str] = set()
        self._lock = threading.Lock()

    def register_ignore_hash(self, content_hash: str):
        """Register a hash that should be ignored by the next detection cycle."""
        with self._lock:
            self._ignored_hashes.add(content_hash)
            self.last_hash = content_hash

    def start(self):
        """Start the background monitoring thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="ClipboardMonitor")
        self._thread.start()

    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _get_offered_targets(self) -> Set[str]:
        """
        Query available clipboard targets.
        Uses xclip because it queries XWayland/X11 directly without creating
        temporary Wayland surfaces (which cause screen flickering/blinking).
        """
        if HAS_XCLIP:
            try:
                proc = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=0.3,
                    check=False
                )
                if proc.returncode == 0:
                    lines = [line.strip() for line in proc.stdout.decode("utf-8", errors="ignore").splitlines()]
                    return {line for line in lines if line}
            except Exception:
                pass
        return set()

    def _fetch_image_bytes(self) -> Optional[bytes]:
        if HAS_XCLIP:
            try:
                proc = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=1.0,
                    check=False
                )
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout
            except Exception:
                pass
        return None

    def _fetch_text(self) -> Optional[str]:
        if HAS_XCLIP:
            try:
                proc = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=0.5,
                    check=False
                )
                if proc.returncode == 0:
                    return proc.stdout.decode("utf-8", errors="replace")
            except Exception:
                pass
        return None

    def _monitor_loop(self):
        while self._running:
            try:
                self._check_clipboard()
            except Exception:
                pass
            time.sleep(POLL_INTERVAL_SECONDS)

    def _check_clipboard(self):
        targets = self._get_offered_targets()
        if not targets:
            return

        has_image = bool(targets.intersection(IMAGE_TARGETS))

        if has_image:
            img_bytes = self._fetch_image_bytes()
            if not img_bytes:
                return

            img_hash = hashlib.sha256(img_bytes).hexdigest()

            with self._lock:
                if img_hash in self._ignored_hashes:
                    self._ignored_hashes.remove(img_hash)
                    self.last_hash = img_hash
                    return
                if img_hash == self.last_hash:
                    return
                self.last_hash = img_hash

            # Process image safely
            try:
                pil_img = Image.open(io.BytesIO(img_bytes))
                width, height = pil_img.size
                file_size = len(img_bytes)

                orig_path = IMAGES_DIR / f"{img_hash}.png"
                if not orig_path.exists():
                    with open(orig_path, "wb") as f:
                        f.write(img_bytes)

                thumb_path = THUMBS_DIR / f"{img_hash}_thumb.png"
                if not thumb_path.exists():
                    thumb_img = pil_img.copy()
                    resample_filter = getattr(Image.Resampling, "LANCZOS", Image.LANCZOS if hasattr(Image, "LANCZOS") else 1)
                    thumb_img.thumbnail(THUMBNAIL_MAX_SIZE, resample_filter)
                    thumb_img.save(thumb_path, format="PNG")

                preview = f"{width} × {height} • {pil_img.format or 'PNG'} • {human_readable_size(file_size)}"

                self.storage.add_or_touch_image(
                    image_path=str(orig_path),
                    thumbnail_path=str(thumb_path),
                    preview_text=preview,
                    width=width,
                    height=height,
                    file_size=file_size,
                    content_hash=img_hash
                )

                if self.on_change_callback:
                    self.on_change_callback()
            except Exception:
                pass
            return

        has_text = bool(targets.intersection(TEXT_TARGETS))
        if has_text:
            text = self._fetch_text()
            if text is None:
                return

            if not text.strip():
                return

            text_bytes = text.encode("utf-8")
            text_hash = hashlib.sha256(text_bytes).hexdigest()

            with self._lock:
                if text_hash in self._ignored_hashes:
                    self._ignored_hashes.remove(text_hash)
                    self.last_hash = text_hash
                    return
                if text_hash == self.last_hash:
                    return
                self.last_hash = text_hash

            lines = text.splitlines()
            line_count = len(lines)
            char_count = len(text)

            preview_lines = lines[:4]
            preview = "\n".join(preview_lines)
            if len(preview) > 300:
                preview = preview[:297] + "..."

            self.storage.add_or_touch_text(
                content=text,
                preview_text=preview,
                char_count=char_count,
                line_count=line_count,
                content_hash=text_hash
            )

            if self.on_change_callback:
                self.on_change_callback()

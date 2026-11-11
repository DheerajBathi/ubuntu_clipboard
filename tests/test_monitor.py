"""Test clipboard monitor and image processing."""
import io
import os
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from winclip.storage import ClipboardStorage
from winclip.monitor import ClipboardMonitor, human_readable_size


class TestMonitor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.storage = ClipboardStorage(self.db_path)
        self.monitor = ClipboardMonitor(self.storage)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_human_readable_size(self):
        self.assertEqual(human_readable_size(500), "500 B")
        self.assertEqual(human_readable_size(1024 * 50), "50.0 KB")
        self.assertEqual(human_readable_size(1024 * 1024 * 2), "2.0 MB")

    def test_image_processing_and_storage(self):
        # Create a test image
        img = Image.new("RGBA", (200, 100), color=(255, 0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        # Save manually to test image add
        orig_path = Path(self.temp_dir.name) / "test_img.png"
        thumb_path = Path(self.temp_dir.name) / "test_thumb.png"
        with open(orig_path, "wb") as f:
            f.write(img_bytes)

        img.thumbnail((100, 50))
        img.save(thumb_path, format="PNG")

        item_id = self.storage.add_or_touch_image(
            image_path=str(orig_path),
            thumbnail_path=str(thumb_path),
            preview_text="200 × 100 • PNG • 500 B",
            width=200,
            height=100,
            file_size=len(img_bytes),
            content_hash="test_img_hash_1"
        )
        self.assertIsNotNone(item_id)

        items = self.storage.get_items("image")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["width"], 200)
        self.assertEqual(items[0]["height"], 100)
        self.assertEqual(items[0]["item_type"], "image")


if __name__ == "__main__":
    unittest.main()

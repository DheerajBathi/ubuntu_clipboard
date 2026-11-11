"""Unit tests for UI helpers."""
import time
import unittest
from winclip.ui import format_relative_time, detect_flavor


class TestUIHelpers(unittest.TestCase):
    def test_format_relative_time(self):
        now = time.time()
        self.assertEqual(format_relative_time(now - 10), "Just now")
        self.assertEqual(format_relative_time(now - 120), "2m ago")
        self.assertEqual(format_relative_time(now - 7200), "2h ago")
        self.assertEqual(format_relative_time(now - 86400 * 2), "2d ago")

    def test_detect_flavor_color(self):
        flavor, info = detect_flavor({"item_type": "text", "content": "#0078d4"})
        self.assertEqual(flavor, "color")
        self.assertEqual(info, "#0078d4")

        flavor, info = detect_flavor({"item_type": "text", "content": "rgb(255, 0, 128)"})
        self.assertEqual(flavor, "color")

    def test_detect_flavor_link(self):
        flavor, info = detect_flavor({"item_type": "text", "content": "https://github.com/torvalds/linux"})
        self.assertEqual(flavor, "link")
        self.assertEqual(info, "github.com")

    def test_detect_flavor_command(self):
        flavor, _ = detect_flavor({"item_type": "text", "content": "git status --short"})
        self.assertEqual(flavor, "command")

        flavor, _ = detect_flavor({"item_type": "text", "content": "docker run -it ubuntu:latest"})
        self.assertEqual(flavor, "command")

    def test_detect_flavor_code(self):
        code = "def hello():\n    return 'world'"
        flavor, _ = detect_flavor({"item_type": "text", "content": code})
        self.assertEqual(flavor, "code")

    def test_detect_flavor_image(self):
        flavor, _ = detect_flavor({"item_type": "image", "content": "/path/to/img.png"})
        self.assertEqual(flavor, "image")


if __name__ == "__main__":
    unittest.main()

"""Unit tests for storage."""
import unittest
import tempfile
import os
from pathlib import Path
from winclip.storage import ClipboardStorage

class TestStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_clipboard.db"
        self.storage = ClipboardStorage(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_get_text(self):
        item_id = self.storage.add_or_touch_text(
            content="Hello World",
            preview_text="Hello World",
            char_count=11,
            line_count=1,
            content_hash="hash1"
        )
        self.assertIsNotNone(item_id)
        items = self.storage.get_items("all")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["content"], "Hello World")
        self.assertEqual(items[0]["item_type"], "text")
        self.assertEqual(items[0]["is_pinned"], 0)

    def test_deduplication(self):
        id1 = self.storage.add_or_touch_text("Repeat Text", "Repeat Text", 11, 1, "hash_repeat")
        id2 = self.storage.add_or_touch_text("Repeat Text", "Repeat Text", 11, 1, "hash_repeat")
        self.assertEqual(id1, id2)
        items = self.storage.get_items("all")
        self.assertEqual(len(items), 1)

    def test_pin_and_filter(self):
        id1 = self.storage.add_or_touch_text("Item 1", "Item 1", 6, 1, "h1")
        id2 = self.storage.add_or_touch_text("Item 2", "Item 2", 6, 1, "h2")
        
        self.storage.toggle_pin(id1)
        
        pinned = self.storage.get_items("pinned")
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0]["id"], id1)

    def test_clear_unpinned(self):
        id1 = self.storage.add_or_touch_text("Pinned", "Pinned", 6, 1, "h_pin")
        id2 = self.storage.add_or_touch_text("Unpinned", "Unpinned", 8, 1, "h_unpin")
        self.storage.toggle_pin(id1)

        cleared_count = self.storage.clear_unpinned()
        self.assertEqual(cleared_count, 1)

        items = self.storage.get_items("all")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], id1)

    def test_search(self):
        self.storage.add_or_touch_text("Apple banana cherry", "Apple banana cherry", 19, 1, "h_fruit")
        self.storage.add_or_touch_text("Dog cat mouse", "Dog cat mouse", 13, 1, "h_animal")

        results = self.storage.get_items(query="banana")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["content_hash"], "h_fruit")

    def test_counts_and_link_filter(self):
        self.storage.add_or_touch_text("https://example.com", "https://example.com", 19, 1, "h_url1")
        self.storage.add_or_touch_text("http://test.org/path", "http://test.org/path", 20, 1, "h_url2")
        id_text = self.storage.add_or_touch_text("Regular text note", "Regular text note", 17, 1, "h_text")
        self.storage.toggle_pin(id_text)

        counts = self.storage.get_counts()
        self.assertEqual(counts["all"], 3)
        self.assertEqual(counts["link"], 2)
        self.assertEqual(counts["text"], 3)
        self.assertEqual(counts["pinned"], 1)

        links = self.storage.get_items(filter_type="link")
        self.assertEqual(len(links), 2)
        for link in links:
            self.assertTrue(link["content"].startswith(("http://", "https://")))

if __name__ == "__main__":
    unittest.main()

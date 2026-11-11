"""Database storage layer for clipboard history."""
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import DB_PATH, MAX_ITEMS


class ClipboardStorage:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS clipboard_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT UNIQUE NOT NULL,
                thumbnail_path TEXT,
                preview_text TEXT,
                char_count INTEGER DEFAULT 0,
                line_count INTEGER DEFAULT 0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                file_size INTEGER DEFAULT 0,
                is_pinned INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_ordering 
            ON clipboard_items(is_pinned DESC, updated_at DESC);
            """)
            conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_items_hash 
            ON clipboard_items(content_hash);
            """)
            conn.commit()

    def get_latest_hash(self) -> Optional[str]:
        """Get the hash of the most recently copied item."""
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT content_hash FROM clipboard_items ORDER BY updated_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            return row["content_hash"] if row else None

    def add_or_touch_text(
        self,
        content: str,
        preview_text: str,
        char_count: int,
        line_count: int,
        content_hash: str
    ) -> int:
        now = time.time()
        with self._connection() as conn:
            # Check if hash already exists
            cur = conn.execute(
                "SELECT id, is_pinned FROM clipboard_items WHERE content_hash = ?",
                (content_hash,)
            )
            row = cur.fetchone()
            if row:
                item_id = row["id"]
                conn.execute(
                    "UPDATE clipboard_items SET updated_at = ? WHERE id = ?",
                    (now, item_id)
                )
                conn.commit()
                return item_id
            else:
                cur = conn.execute("""
                INSERT INTO clipboard_items (
                    item_type, content, content_hash, thumbnail_path, preview_text,
                    char_count, line_count, width, height, file_size, is_pinned,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "text", content, content_hash, None, preview_text,
                    char_count, line_count, 0, 0, len(content.encode("utf-8")),
                    0, now, now
                ))
                item_id = cur.lastrowid
                conn.commit()
                self._prune(conn)
                return item_id

    def add_or_touch_image(
        self,
        image_path: str,
        thumbnail_path: str,
        preview_text: str,
        width: int,
        height: int,
        file_size: int,
        content_hash: str
    ) -> int:
        now = time.time()
        with self._connection() as conn:
            cur = conn.execute(
                "SELECT id FROM clipboard_items WHERE content_hash = ?",
                (content_hash,)
            )
            row = cur.fetchone()
            if row:
                item_id = row["id"]
                conn.execute(
                    "UPDATE clipboard_items SET updated_at = ? WHERE id = ?",
                    (now, item_id)
                )
                conn.commit()
                return item_id
            else:
                cur = conn.execute("""
                INSERT INTO clipboard_items (
                    item_type, content, content_hash, thumbnail_path, preview_text,
                    char_count, line_count, width, height, file_size, is_pinned,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    "image", image_path, content_hash, thumbnail_path, preview_text,
                    0, 0, width, height, file_size,
                    0, now, now
                ))
                item_id = cur.lastrowid
                conn.commit()
                self._prune(conn)
                return item_id

    def get_items(
        self,
        filter_type: str = "all",
        query: str = "",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        clauses = []
        params: List[Any] = []

        if filter_type == "text":
            clauses.append("item_type = 'text'")
        elif filter_type == "image":
            clauses.append("item_type = 'image'")
        elif filter_type == "pinned":
            clauses.append("is_pinned = 1")

        if query.strip():
            # Search both in preview text and content for text, or preview for image
            clauses.append("(preview_text LIKE ? OR (item_type = 'text' AND content LIKE ?))")
            term = f"%{query.strip()}%"
            params.extend([term, term])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query_sql = f"""
        SELECT * FROM clipboard_items
        {where_sql}
        ORDER BY is_pinned DESC, updated_at DESC
        LIMIT ?
        """
        params.append(limit)

        with self._connection() as conn:
            cur = conn.execute(query_sql, params)
            return [dict(row) for row in cur.fetchall()]

    def get_item_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cur = conn.execute("SELECT * FROM clipboard_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def toggle_pin(self, item_id: int) -> bool:
        with self._connection() as conn:
            cur = conn.execute("SELECT is_pinned FROM clipboard_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if not row:
                return False
            new_val = 0 if row["is_pinned"] else 1
            conn.execute("UPDATE clipboard_items SET is_pinned = ? WHERE id = ?", (new_val, item_id))
            conn.commit()
            return bool(new_val)

    def delete_item(self, item_id: int) -> bool:
        with self._connection() as conn:
            cur = conn.execute("SELECT item_type, content, thumbnail_path FROM clipboard_items WHERE id = ?", (item_id,))
            row = cur.fetchone()
            if not row:
                return False

            if row["item_type"] == "image":
                # Remove file from disk
                for fpath in (row["content"], row["thumbnail_path"]):
                    if fpath and os.path.exists(fpath):
                        try:
                            os.remove(fpath)
                        except OSError:
                            pass

            conn.execute("DELETE FROM clipboard_items WHERE id = ?", (item_id,))
            conn.commit()
            return True

    def clear_unpinned(self) -> int:
        """Clear all unpinned items and their files. Returns deleted count."""
        with self._connection() as conn:
            cur = conn.execute("SELECT item_type, content, thumbnail_path FROM clipboard_items WHERE is_pinned = 0")
            rows = cur.fetchall()
            for r in rows:
                if r["item_type"] == "image":
                    for fpath in (r["content"], r["thumbnail_path"]):
                        if fpath and os.path.exists(fpath):
                            try:
                                os.remove(fpath)
                            except OSError:
                                pass

            del_cur = conn.execute("DELETE FROM clipboard_items WHERE is_pinned = 0")
            count = del_cur.rowcount
            conn.commit()
            return count

    def _prune(self, conn: sqlite3.Connection):
        """Keep database within MAX_ITEMS limit for unpinned items."""
        cur = conn.execute("SELECT COUNT(*) AS total FROM clipboard_items")
        total = cur.fetchone()["total"]
        if total > MAX_ITEMS:
            excess = total - MAX_ITEMS
            # Select oldest unpinned items to delete
            cur = conn.execute("""
            SELECT id, item_type, content, thumbnail_path
            FROM clipboard_items
            WHERE is_pinned = 0
            ORDER BY updated_at ASC
            LIMIT ?
            """, (excess,))
            rows = cur.fetchall()
            ids_to_del = []
            for r in rows:
                ids_to_del.append(r["id"])
                if r["item_type"] == "image":
                    for fpath in (r["content"], r["thumbnail_path"]):
                        if fpath and os.path.exists(fpath):
                            try:
                                os.remove(fpath)
                            except OSError:
                                pass
            if ids_to_del:
                placeholders = ",".join("?" * len(ids_to_del))
                conn.execute(f"DELETE FROM clipboard_items WHERE id IN ({placeholders})", ids_to_del)

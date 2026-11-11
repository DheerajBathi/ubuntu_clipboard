"""Windows-style Clipboard GUI using GTK 3 with floating utility window hints."""
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango

from .config import (
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    CSS_PATH,
)
from .storage import ClipboardStorage
from .copier import ClipboardCopier


def format_relative_time(timestamp: float) -> str:
    """Return human-friendly relative time string."""
    diff = time.time() - timestamp
    if diff < 60:
        return "Just now"
    elif diff < 3600:
        mins = max(1, int(diff // 60))
        return f"{mins}m ago"
    elif diff < 86400:
        hours = int(diff // 3600)
        return f"{hours}h ago"
    elif diff < 86400 * 7:
        days = int(diff // 86400)
        return f"{days}d ago"
    else:
        return time.strftime("%b %d", time.localtime(timestamp))


class ClipboardWindow:
    def __init__(
        self,
        storage: ClipboardStorage,
        copier: ClipboardCopier,
        on_hide_callback: Optional[Callable[[], None]] = None
    ):
        self.storage = storage
        self.copier = copier
        self.on_hide_callback = on_hide_callback

        self.current_filter = "all"
        self.search_query = ""
        self.is_present = False
        self._opened_at = 0.0

        self._setup_css()
        self._build_ui()

    def _setup_css(self):
        screen = Gdk.Screen.get_default()
        if screen and CSS_PATH.exists():
            provider = Gtk.CssProvider()
            try:
                provider.load_from_path(str(CSS_PATH))
                Gtk.StyleContext.add_provider_for_screen(
                    screen,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
            except Exception as e:
                print(f"CSS loading notice: {e}")

    def _build_ui(self):
        # Create Floating Utility Window (never shows in taskbar/notch)
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title("Clipboard")
        self.window.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.window.set_position(Gtk.WindowPosition.CENTER)

        # Critical utility window hints to prevent desktop notch flickering
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_keep_above(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        self.window.get_style_context().add_class("winclip-window")

        # Intercept window close to hide instead of destroy
        self.window.connect("delete-event", lambda w, e: self.hide() or True)
        self.window.connect("key-press-event", self._on_key_press)
        self.window.connect("focus-out-event", self._on_focus_out)

        # Main vertical container
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.add(root_box)

        # Header bar
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.get_style_context().add_class("winclip-header")

        # Title with Icon
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.set_hexpand(True)
        title_icon = Gtk.Image.new_from_icon_name("edit-paste-symbolic", Gtk.IconSize.MENU)
        title_label = Gtk.Label(label="Clipboard History")
        title_label.get_style_context().add_class("winclip-title")
        title_box.pack_start(title_icon, False, False, 0)
        title_box.pack_start(title_label, False, False, 0)
        header_box.pack_start(title_box, True, True, 0)

        # "Clear all" button
        self.clear_btn = Gtk.Button(label="Clear all")
        self.clear_btn.get_style_context().add_class("winclip-clear-btn")
        self.clear_btn.set_tooltip_text("Clear all unpinned clipboard items")
        self.clear_btn.connect("clicked", self._on_clear_all_clicked)
        header_box.pack_start(self.clear_btn, False, False, 0)

        # Close button
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.get_style_context().add_class("clip-action-btn")
        close_btn.set_tooltip_text("Close (Esc)")
        close_btn.connect("clicked", lambda b: self.hide())
        header_box.pack_start(close_btn, False, False, 0)

        root_box.pack_start(header_box, False, False, 0)

        # Search Bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_box.get_style_context().add_class("winclip-search")
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Type to search clipboard history...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        search_box.pack_start(self.search_entry, True, True, 0)
        root_box.pack_start(search_box, False, False, 0)

        # Filter Tabs (Pills)
        tabs_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        tabs_box.get_style_context().add_class("winclip-tabs")
        self.tab_buttons: Dict[str, Gtk.Button] = {}

        tabs_meta = [
            ("all", "📋 All"),
            ("text", "📝 Text"),
            ("image", "🖼️ Images"),
            ("pinned", "📌 Pinned"),
        ]

        for filter_key, label_text in tabs_meta:
            btn = Gtk.Button(label=label_text)
            btn.get_style_context().add_class("winclip-tab-btn")
            if filter_key == self.current_filter:
                btn.get_style_context().add_class("active")
            btn.connect("clicked", self._on_tab_clicked, filter_key)
            self.tab_buttons[filter_key] = btn
            tabs_box.pack_start(btn, False, False, 0)

        root_box.pack_start(tabs_box, False, False, 0)

        # Scrolled List Container
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_hexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.get_style_context().add_class("winclip-list-scroll")

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.list_box.get_style_context().add_class("winclip-list")
        self.scrolled.add(self.list_box)
        root_box.pack_start(self.scrolled, True, True, 0)

        # Footer Hint
        hint_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        hint_box.get_style_context().add_class("winclip-hint-footer")
        hint_label = Gtk.Label(label="Click card to copy • Super+V to toggle • Esc to close")
        hint_label.set_hexpand(True)
        hint_label.set_xalign(0.5)
        hint_box.pack_start(hint_label, True, True, 0)
        root_box.pack_start(hint_box, False, False, 0)

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _on_focus_out(self, widget, event):
        # Auto-dismiss on click outside (only after 400ms to avoid opening blips)
        if self.is_present and (time.time() - self._opened_at > 0.4):
            self.hide()
        return False

    def _on_tab_clicked(self, button: Gtk.Button, filter_key: str):
        if self.current_filter == filter_key:
            return
        self.current_filter = filter_key
        for k, btn in self.tab_buttons.items():
            if k == filter_key:
                btn.get_style_context().add_class("active")
            else:
                btn.get_style_context().remove_class("active")
        self.refresh()

    def _on_search_changed(self, entry: Gtk.SearchEntry):
        self.search_query = entry.get_text()
        self.refresh()

    def _on_clear_all_clicked(self, button: Gtk.Button):
        self.storage.clear_unpinned()
        self.refresh()

    def refresh(self):
        """Fetch updated items from database and rebuild cards."""
        for child in self.list_box.get_children():
            self.list_box.remove(child)

        items = self.storage.get_items(
            filter_type=self.current_filter,
            query=self.search_query,
            limit=100
        )

        if not items:
            self._render_empty_state()
            self.list_box.show_all()
            return

        for item in items:
            card_widget = self._create_item_card(item)
            self.list_box.pack_start(card_widget, False, False, 0)

        self.list_box.show_all()

    def _render_empty_state(self):
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty_box.get_style_context().add_class("winclip-empty-state")
        empty_box.set_vexpand(True)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("edit-paste-symbolic", Gtk.IconSize.DIALOG)
        empty_box.pack_start(icon, False, False, 0)

        title = Gtk.Label(label="Clipboard is empty")
        title.get_style_context().add_class("winclip-empty-title")
        empty_box.pack_start(title, False, False, 0)

        subtitle_text = "Copy text or images from any app, and they will appear here."
        if self.search_query:
            subtitle_text = f"No results found for '{self.search_query}'."
        subtitle = Gtk.Label(label=subtitle_text)
        subtitle.get_style_context().add_class("winclip-empty-subtitle")
        empty_box.pack_start(subtitle, False, False, 0)

        self.list_box.pack_start(empty_box, True, True, 20)

    def _create_item_card(self, item: Dict[str, Any]) -> Gtk.Widget:
        event_box = Gtk.EventBox()
        event_box.set_visible_window(False)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.get_style_context().add_class("clip-card")
        if item.get("is_pinned"):
            card.get_style_context().add_class("pinned")

        item_type = item.get("item_type", "text")
        item_id = item["id"]
        content_hash = item["content_hash"]

        # Content area
        if item_type == "text":
            text_content = item.get("content", "")
            preview_lbl = Gtk.Label(label=text_content)
            preview_lbl.get_style_context().add_class("clip-text-content")
            preview_lbl.set_line_wrap(True)
            preview_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            preview_lbl.set_lines(4)
            preview_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            preview_lbl.set_xalign(0.0)
            preview_lbl.set_selectable(False)
            card.pack_start(preview_lbl, False, False, 0)
        else:
            # Image card
            thumb_path = item.get("thumbnail_path") or item.get("content")
            if thumb_path and os.path.exists(thumb_path):
                img_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                img_box.get_style_context().add_class("clip-image-box")
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        thumb_path, 340, 130, True
                    )
                    image_widget = Gtk.Image.new_from_pixbuf(pixbuf)
                    img_box.pack_start(image_widget, False, False, 0)
                    card.pack_start(img_box, False, False, 0)
                except Exception:
                    pass

        # Footer Row (Metadata & Action Buttons)
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.get_style_context().add_class("clip-footer")

        # Metadata
        if item_type == "text":
            meta_str = f"{item.get('char_count', 0)} chars • {item.get('line_count', 0)} lines"
        else:
            meta_str = item.get("preview_text", "Image")

        meta_lbl = Gtk.Label(label=meta_str)
        meta_lbl.get_style_context().add_class("clip-meta-badge")
        meta_lbl.set_xalign(0.0)
        footer.pack_start(meta_lbl, False, False, 0)

        time_lbl = Gtk.Label(label=format_relative_time(item.get("updated_at", time.time())))
        time_lbl.get_style_context().add_class("clip-time-badge")
        footer.pack_start(time_lbl, False, False, 0)

        # Spacer
        spacer = Gtk.Box()
        footer.pack_start(spacer, True, True, 0)

        # Pin button
        is_pinned = bool(item.get("is_pinned"))
        pin_btn = Gtk.Button()
        pin_btn.get_style_context().add_class("clip-action-btn")
        pin_btn.get_style_context().add_class("clip-pin-btn")
        if is_pinned:
            pin_btn.get_style_context().add_class("pinned")
            pin_icon = Gtk.Image.new_from_icon_name("starred-symbolic", Gtk.IconSize.MENU)
            pin_btn.set_tooltip_text("Unpin item")
        else:
            pin_icon = Gtk.Image.new_from_icon_name("non-starred-symbolic", Gtk.IconSize.MENU)
            pin_btn.set_tooltip_text("Pin to top")
        pin_btn.set_image(pin_icon)
        pin_btn.connect("clicked", self._on_pin_clicked, item_id)
        footer.pack_start(pin_btn, False, False, 0)

        # Delete button
        del_btn = Gtk.Button()
        del_btn.get_style_context().add_class("clip-action-btn")
        del_btn.get_style_context().add_class("clip-del-btn")
        del_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.MENU)
        del_btn.set_image(del_icon)
        del_btn.set_tooltip_text("Delete from history")
        del_btn.connect("clicked", self._on_delete_clicked, item_id)
        footer.pack_start(del_btn, False, False, 0)

        card.pack_start(footer, False, False, 0)
        event_box.add(card)

        # Click event on card to copy
        event_box.connect("button-release-event", self._on_card_clicked, item)

        return event_box

    def _on_card_clicked(self, widget, event, item: Dict[str, Any]):
        # Ignore if user clicked pin or delete buttons (they consume their own events)
        item_type = item.get("item_type", "text")
        content_hash = item.get("content_hash")

        if item_type == "text":
            self.copier.copy_text(item.get("content", ""), content_hash=content_hash)
        else:
            self.copier.copy_image(item.get("content", ""), content_hash=content_hash)

        # Update updated_at so it bumps to top
        if item_type == "text":
            self.storage.add_or_touch_text(
                item.get("content", ""),
                item.get("preview_text", ""),
                item.get("char_count", 0),
                item.get("line_count", 0),
                content_hash
            )
        else:
            self.storage.add_or_touch_image(
                item.get("content", ""),
                item.get("thumbnail_path", ""),
                item.get("preview_text", ""),
                item.get("width", 0),
                item.get("height", 0),
                item.get("file_size", 0),
                content_hash
            )

        self.hide()
        return True

    def _on_pin_clicked(self, button: Gtk.Button, item_id: int):
        self.storage.toggle_pin(item_id)
        self.refresh()

    def _on_delete_clicked(self, button: Gtk.Button, item_id: int):
        self.storage.delete_item(item_id)
        self.refresh()

    def show(self):
        """Show and present the clipboard window."""
        self.refresh()
        self.is_present = True
        self._opened_at = time.time()
        self.window.show_all()
        self.window.present()
        GLib.idle_add(self.search_entry.grab_focus)

    def hide(self):
        """Hide the clipboard window."""
        self.window.hide()
        self.is_present = False
        if self.on_hide_callback:
            self.on_hide_callback()

    def toggle(self):
        """Toggle clipboard window visibility."""
        if self.is_present and self.window.get_visible():
            self.hide()
        else:
            self.show()

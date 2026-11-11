"""Windows 11 Fluent-style Clipboard GUI using GTK 3 with floating utility window hints."""
import os
import re
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
import cairo

from .config import (
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    CSS_PATH,
    ICON_PATH,
)
from .storage import ClipboardStorage
from .copier import ClipboardCopier


def format_relative_time(timestamp: float) -> str:
    """Return human-friendly relative time string."""
    diff = time.time() - timestamp
    if diff < 45:
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


def detect_flavor(item: Dict[str, Any]) -> Tuple[str, str]:
    """Detect content flavor: ('image', 'link', 'color', 'code', 'command', 'text')."""
    if item.get("item_type") == "image":
        return "image", ""

    text = item.get("content", "").strip()
    if not text:
        return "text", ""

    # Check Color Hex / RGB
    color_match = re.match(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", text)
    if color_match or text.startswith(("rgb(", "rgba(", "hsl(", "hsla(")):
        return "color", text

    # Check URL / Link
    if text.startswith(("http://", "https://", "ftp://")):
        try:
            parsed = urllib.parse.urlparse(text)
            domain = parsed.netloc or "link"
            return "link", domain
        except Exception:
            return "link", "link"

    # Check Shell Command
    first_line = text.splitlines()[0].strip()
    cmd_prefixes = ("sudo ", "git ", "docker ", "npm ", "yarn ", "pnpm ", "pip ", "curl ", "cargo ", "go ", "apt ", "systemctl ")
    if first_line.startswith(cmd_prefixes) and len(text.splitlines()) <= 2:
        return "command", ""

    # Check Code Snippet
    lines = text.splitlines()
    if len(lines) >= 2:
        code_indicators = (
            "def ", "class ", "import ", "from ", "function", "const ", "let ",
            "var ", "return ", "if (", "for (", "while (", "try {", "catch (",
            "SELECT ", "INSERT ", "UPDATE ", "DELETE FROM", "CREATE TABLE",
            "<html>", "<div", "<?php", "namespace ", "public class", "fn main"
        )
        if any(ind in text for ind in code_indicators) or (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
            return "code", ""

    return "text", ""


def create_color_swatch_widget(color_str: str) -> Optional[Gtk.DrawingArea]:
    """Create a sleek rounded color swatch circle/rect for color preview."""
    rgba = Gdk.RGBA()
    if not rgba.parse(color_str):
        return None

    area = Gtk.DrawingArea()
    area.set_size_request(22, 22)

    def on_draw(widget, cr):
        x, y, w, h, r = 2, 2, 18, 18, 5
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -1.5707963, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 1.5707963)
        cr.arc(x + r, y + h - r, r, 1.5707963, 3.1415926)
        cr.arc(x + r, y + r, r, 3.1415926, 4.7123889)
        cr.close_path()

        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.fill_preserve()

        # Crisp border
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.25)
        cr.set_line_width(1.0)
        cr.stroke()
        return False

    area.connect("draw", on_draw)
    return area


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

        self.card_data: List[Dict[str, Any]] = []
        self.card_widgets: List[Gtk.Widget] = []
        self.selected_index: int = -1

        self.tab_buttons: Dict[str, Gtk.Button] = {}
        self.tab_badge_labels: Dict[str, Gtk.Label] = {}
        self._toast_timeout_id = None

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
        # Create Floating Utility Window
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title("Clipboard")
        self.window.set_default_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.window.set_position(Gtk.WindowPosition.CENTER)

        # Enable true RGBA visual for smooth rounded translucent borders
        screen = self.window.get_screen()
        if screen:
            visual = screen.get_rgba_visual()
            if visual:
                self.window.set_visual(visual)
        self.window.set_app_paintable(True)

        # Window hints to keep it floating, out of taskbar
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_keep_above(True)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        if ICON_PATH.exists():
            try:
                self.window.set_icon_from_file(str(ICON_PATH))
            except Exception:
                pass

        self.window.get_style_context().add_class("winclip-window")

        # Intercept window events
        self.window.connect("delete-event", lambda w, e: self.hide() or True)
        self.window.connect("key-press-event", self._on_key_press)
        self.window.connect("focus-out-event", self._on_focus_out)

        # Root Overlay Container (for toast notifications over list)
        self.overlay = Gtk.Overlay()
        self.window.add(self.overlay)

        # Main vertical container
        root_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.overlay.add(root_box)

        # ==========================================
        # 1. Header Bar
        # ==========================================
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header_box.get_style_context().add_class("winclip-header")

        # Brand / Title Box
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box.set_hexpand(True)

        # Load SVG logo icon or symbolic fallback
        if ICON_PATH.exists():
            try:
                logo_pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(ICON_PATH), 22, 22, True)
                brand_img = Gtk.Image.new_from_pixbuf(logo_pb)
            except Exception:
                brand_img = Gtk.Image.new_from_icon_name("edit-paste-symbolic", Gtk.IconSize.MENU)
        else:
            brand_img = Gtk.Image.new_from_icon_name("edit-paste-symbolic", Gtk.IconSize.MENU)

        brand_img.get_style_context().add_class("winclip-brand-icon")
        title_box.pack_start(brand_img, False, False, 0)

        title_label = Gtk.Label(label="Clipboard")
        title_label.get_style_context().add_class("winclip-title")
        title_box.pack_start(title_label, False, False, 0)

        self.count_badge_label = Gtk.Label(label="0 items")
        self.count_badge_label.get_style_context().add_class("winclip-count-badge")
        title_box.pack_start(self.count_badge_label, False, False, 0)

        header_box.pack_start(title_box, True, True, 0)

        # "Clear all" button with icon
        self.clear_btn = Gtk.Button()
        clear_content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        clear_icon = Gtk.Image.new_from_icon_name("edit-clear-all-symbolic", Gtk.IconSize.MENU)
        clear_lbl = Gtk.Label(label="Clear")
        clear_content_box.pack_start(clear_icon, False, False, 0)
        clear_content_box.pack_start(clear_lbl, False, False, 0)
        self.clear_btn.add(clear_content_box)
        self.clear_btn.get_style_context().add_class("winclip-clear-btn")
        self.clear_btn.set_tooltip_text("Clear unpinned clipboard items")
        self.clear_btn.connect("clicked", self._on_clear_all_clicked)
        header_box.pack_start(self.clear_btn, False, False, 0)

        # Close button
        close_btn = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.get_style_context().add_class("winclip-close-btn")
        close_btn.set_tooltip_text("Close (Esc)")
        close_btn.connect("clicked", lambda b: self.hide())
        header_box.pack_start(close_btn, False, False, 0)

        root_box.pack_start(header_box, False, False, 0)

        # ==========================================
        # 2. Modern Search Bar
        # ==========================================
        search_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        search_container.get_style_context().add_class("winclip-search-container")

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.get_style_context().add_class("winclip-search-entry")
        self.search_entry.set_placeholder_text("Search clipboard, links, code...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect("key-press-event", self._on_search_key_press)
        search_container.pack_start(self.search_entry, True, True, 0)

        root_box.pack_start(search_container, False, False, 0)

        # ==========================================
        # 3. Filter Tabs (Segmented Control Pills)
        # ==========================================
        tabs_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        tabs_container.get_style_context().add_class("winclip-tabs-container")

        tabs_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        tabs_bar.get_style_context().add_class("winclip-tabs-bar")
        tabs_bar.set_hexpand(True)

        tabs_meta = [
            ("all", "All"),
            ("text", "Text"),
            ("link", "Links"),
            ("image", "Images"),
            ("pinned", "Pinned"),
        ]

        for filter_key, label_text in tabs_meta:
            btn = Gtk.Button()
            btn.get_style_context().add_class("winclip-tab-btn")

            btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            lbl = Gtk.Label(label=label_text)
            counter = Gtk.Label(label="0")
            counter.get_style_context().add_class("winclip-tab-counter")

            btn_box.pack_start(lbl, False, False, 0)
            btn_box.pack_start(counter, False, False, 0)
            btn.add(btn_box)

            if filter_key == self.current_filter:
                btn.get_style_context().add_class("active")

            btn.connect("clicked", self._on_tab_clicked, filter_key)
            self.tab_buttons[filter_key] = btn
            self.tab_badge_labels[filter_key] = counter
            tabs_bar.pack_start(btn, True, True, 0)

        tabs_container.pack_start(tabs_bar, True, True, 0)
        root_box.pack_start(tabs_container, False, False, 0)

        # ==========================================
        # 4. Scrolled List Container
        # ==========================================
        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_vexpand(True)
        self.scrolled.set_hexpand(True)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.get_style_context().add_class("winclip-list-scroll")

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.list_box.get_style_context().add_class("winclip-list")
        self.scrolled.add(self.list_box)
        root_box.pack_start(self.scrolled, True, True, 0)

        # ==========================================
        # 5. Keyboard Hints Footer
        # ==========================================
        hint_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hint_box.get_style_context().add_class("winclip-hint-footer")

        hints_lbl = Gtk.Label()
        hints_lbl.set_markup(
            "<span alpha='70%'>Press</span> "
            "<span bgcolor='#2a2a30' fgcolor='#f4f4f5'> ↵ </span> <span alpha='70%'>Copy · </span>"
            "<span bgcolor='#2a2a30' fgcolor='#f4f4f5'> P </span> <span alpha='70%'>Pin · </span>"
            "<span bgcolor='#2a2a30' fgcolor='#f4f4f5'> Del </span> <span alpha='70%'>Delete</span>"
        )
        hint_box.pack_start(hints_lbl, False, False, 0)

        spacer = Gtk.Box()
        hint_box.pack_start(spacer, True, True, 0)

        shortcut_lbl = Gtk.Label()
        shortcut_lbl.set_markup("<span bgcolor='#0078d4' fgcolor='#ffffff'><b> Super+V </b></span>")
        hint_box.pack_start(shortcut_lbl, False, False, 0)

        root_box.pack_start(hint_box, False, False, 0)

        # ==========================================
        # 6. Toast Notification Overlay
        # ==========================================
        self.toast_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.toast_box.get_style_context().add_class("winclip-toast")
        self.toast_label = Gtk.Label(label="Copied to clipboard")
        self.toast_box.pack_start(self.toast_label, True, True, 0)
        self.toast_box.set_halign(Gtk.Align.CENTER)
        self.toast_box.set_valign(Gtk.Align.END)
        self.toast_box.set_margin_bottom(52)
        self.toast_box.set_no_show_all(True)
        self.overlay.add_overlay(self.toast_box)
        self.toast_box.hide()

    def show_toast(self, message: str, duration_ms: int = 1500):
        """Display an in-app toast notification."""
        if self._toast_timeout_id:
            GLib.source_remove(self._toast_timeout_id)
            self._toast_timeout_id = None

        self.toast_label.set_text(message)
        self.toast_box.show()

        def _hide_toast():
            self.toast_box.hide()
            self._toast_timeout_id = None
            return False

        self._toast_timeout_id = GLib.timeout_add(duration_ms, _hide_toast)

    def _on_key_press(self, widget, event):
        """Global key navigation."""
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True

        if event.keyval == Gdk.KEY_Down:
            self._move_selection(1)
            return True

        if event.keyval == Gdk.KEY_Up:
            self._move_selection(-1)
            return True

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if 0 <= self.selected_index < len(self.card_data):
                self._on_card_clicked(None, None, self.card_data[self.selected_index])
                return True

        # Quick action keys when search is not active
        if not self.search_entry.has_focus():
            if event.keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
                if 0 <= self.selected_index < len(self.card_data):
                    item_id = self.card_data[self.selected_index]["id"]
                    self._on_delete_clicked(None, item_id)
                    return True

            if event.keyval in (Gdk.KEY_p, Gdk.KEY_P):
                if 0 <= self.selected_index < len(self.card_data):
                    item_id = self.card_data[self.selected_index]["id"]
                    self._on_pin_clicked(None, item_id)
                    return True

            if event.keyval in (Gdk.KEY_o, Gdk.KEY_O):
                if 0 <= self.selected_index < len(self.card_data):
                    item = self.card_data[self.selected_index]
                    if item.get("item_type") == "text" and item.get("content", "").startswith(("http://", "https://")):
                        self._on_open_url_clicked(None, item.get("content", ""))
                        return True

        return False

    def _on_search_key_press(self, widget, event):
        """Handle Down/Enter navigation directly from search box."""
        if event.keyval == Gdk.KEY_Down:
            if self.card_widgets:
                self.selected_index = 0
                self._update_selection_highlight()
                self._scroll_to_selected()
                self.window.set_focus(None)
                return True
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.card_data:
                idx = max(0, self.selected_index)
                if idx < len(self.card_data):
                    self._on_card_clicked(None, None, self.card_data[idx])
                    return True
        elif event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _move_selection(self, delta: int):
        if not self.card_widgets:
            return

        new_index = self.selected_index + delta
        if new_index < 0:
            self.selected_index = -1
            self._update_selection_highlight()
            self.search_entry.grab_focus()
            return

        new_index = min(len(self.card_widgets) - 1, new_index)
        self.selected_index = new_index
        self._update_selection_highlight()
        self._scroll_to_selected()

    def _update_selection_highlight(self):
        for idx, widget in enumerate(self.card_widgets):
            child = widget.get_child()
            if child:
                if idx == self.selected_index:
                    child.get_style_context().add_class("selected")
                else:
                    child.get_style_context().remove_class("selected")

    def _scroll_to_selected(self):
        if not self.card_widgets or self.selected_index < 0 or self.selected_index >= len(self.card_widgets):
            return

        card_widget = self.card_widgets[self.selected_index]
        adj = self.scrolled.get_vadjustment()
        alloc = card_widget.get_allocation()
        val = adj.get_value()
        page_size = adj.get_page_size()

        if alloc.y < val:
            adj.set_value(max(0, alloc.y - 12))
        elif alloc.y + alloc.height > val + page_size:
            adj.set_value(alloc.y + alloc.height - page_size + 12)

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
        count = self.storage.clear_unpinned()
        self.refresh()
        self.show_toast(f"Cleared {count} unpinned items")

    def refresh(self):
        """Fetch updated items from database, update badge counters, and rebuild cards."""
        # 1. Update tab badge counts
        counts = self.storage.get_counts()
        for k, lbl in self.tab_badge_labels.items():
            c = counts.get(k, 0)
            lbl.set_text(str(c))

        total_all = counts.get("all", 0)
        self.count_badge_label.set_text(f"{total_all} items")

        # 2. Clear old widgets
        for child in self.list_box.get_children():
            self.list_box.remove(child)

        self.card_data = []
        self.card_widgets = []
        self.selected_index = -1

        # 3. Query items
        items = self.storage.get_items(
            filter_type=self.current_filter,
            query=self.search_query,
            limit=120
        )

        if not items:
            self._render_empty_state()
            self.list_box.show_all()
            return

        self.card_data = items
        for idx, item in enumerate(items):
            card_widget = self._create_item_card(item, idx)
            self.card_widgets.append(card_widget)
            self.list_box.pack_start(card_widget, False, False, 0)

        # Highlight first item by default
        if self.card_widgets:
            self.selected_index = 0
            self._update_selection_highlight()

        self.list_box.show_all()

    def _render_empty_state(self):
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty_box.get_style_context().add_class("winclip-empty-state")
        empty_box.set_vexpand(True)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)

        if self.search_query:
            icon_name = "system-search-symbolic"
            title_text = "No results found"
            subtitle_text = f"No clipboard items match '{self.search_query}'."
        elif self.current_filter == "pinned":
            icon_name = "starred-symbolic"
            title_text = "No pinned items"
            subtitle_text = "Click the star icon on any card to pin items permanently."
        elif self.current_filter == "link":
            icon_name = "applications-internet-symbolic"
            title_text = "No web links found"
            subtitle_text = "Copy URLs or website links to filter them here."
        elif self.current_filter == "image":
            icon_name = "image-x-generic-symbolic"
            title_text = "No copied images"
            subtitle_text = "Take a screenshot or copy pictures from any app."
        else:
            icon_name = "edit-paste-symbolic"
            title_text = "Clipboard is empty"
            subtitle_text = "Copy text, code, or images from any app, and they will appear here."

        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        empty_box.pack_start(icon, False, False, 0)

        title = Gtk.Label(label=title_text)
        title.get_style_context().add_class("winclip-empty-title")
        empty_box.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label=subtitle_text)
        subtitle.get_style_context().add_class("winclip-empty-subtitle")
        empty_box.pack_start(subtitle, False, False, 0)

        self.list_box.pack_start(empty_box, True, True, 20)

    def _create_item_card(self, item: Dict[str, Any], index: int) -> Gtk.Widget:
        event_box = Gtk.EventBox()
        event_box.set_visible_window(False)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("clip-card")
        if item.get("is_pinned"):
            card.get_style_context().add_class("pinned")

        item_type = item.get("item_type", "text")
        item_id = item["id"]
        flavor, flavor_info = detect_flavor(item)

        # ==========================================
        # Card Header Row (Type Badge + Time + Actions)
        # ==========================================
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.get_style_context().add_class("clip-card-header")

        # Flavor Badge
        badge_lbl = Gtk.Label()
        badge_lbl.get_style_context().add_class("badge-flavor")

        if flavor == "link":
            badge_lbl.set_text(f"🔗 {flavor_info}" if flavor_info else "🔗 Link")
            badge_lbl.get_style_context().add_class("badge-link")
        elif flavor == "code":
            badge_lbl.set_text("</> Code")
            badge_lbl.get_style_context().add_class("badge-code")
        elif flavor == "command":
            badge_lbl.set_text(">_ Command")
            badge_lbl.get_style_context().add_class("badge-code")
        elif flavor == "color":
            badge_lbl.set_text("● Color")
            badge_lbl.get_style_context().add_class("badge-color")
        elif flavor == "image":
            badge_lbl.set_text("🖼️ Image")
            badge_lbl.get_style_context().add_class("badge-image")
        else:
            badge_lbl.set_text("📄 Text")
            badge_lbl.get_style_context().add_class("badge-text")

        header.pack_start(badge_lbl, False, False, 0)

        # Pinned Tag
        if item.get("is_pinned"):
            pin_tag = Gtk.Label(label="📌 Pinned")
            pin_tag.get_style_context().add_class("badge-flavor")
            pin_tag.get_style_context().add_class("badge-pinned")
            header.pack_start(pin_tag, False, False, 0)

        # Relative Timestamp
        time_lbl = Gtk.Label(label=format_relative_time(item.get("updated_at", time.time())))
        time_lbl.get_style_context().add_class("clip-time-badge")
        header.pack_start(time_lbl, False, False, 0)

        # Spacer between tags and action buttons
        header_spacer = Gtk.Box()
        header.pack_start(header_spacer, True, True, 0)

        # Actions on Card Header
        # 1. Open URL in browser (if link)
        if flavor == "link":
            open_btn = Gtk.Button()
            open_btn.get_style_context().add_class("clip-action-btn")
            open_btn.get_style_context().add_class("clip-link-btn")
            open_icon = Gtk.Image.new_from_icon_name("applications-internet-symbolic", Gtk.IconSize.MENU)
            open_btn.set_image(open_icon)
            open_btn.set_tooltip_text("Open URL in Browser")
            open_btn.connect("clicked", lambda b: self._on_open_url_clicked(b, item.get("content", "")))
            header.pack_start(open_btn, False, False, 0)

        # 2. Copy button
        copy_btn = Gtk.Button()
        copy_btn.get_style_context().add_class("clip-action-btn")
        copy_btn.get_style_context().add_class("clip-copy-btn")
        copy_icon = Gtk.Image.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.MENU)
        copy_btn.set_image(copy_icon)
        copy_btn.set_tooltip_text("Copy to clipboard (Enter)")
        copy_btn.connect("clicked", lambda b: self._on_card_clicked(None, None, item))
        header.pack_start(copy_btn, False, False, 0)

        # 3. Pin button
        pin_btn = Gtk.Button()
        pin_btn.get_style_context().add_class("clip-action-btn")
        pin_btn.get_style_context().add_class("clip-pin-btn")
        if item.get("is_pinned"):
            pin_btn.get_style_context().add_class("pinned")
            pin_icon = Gtk.Image.new_from_icon_name("starred-symbolic", Gtk.IconSize.MENU)
            pin_btn.set_tooltip_text("Unpin item (P)")
        else:
            pin_icon = Gtk.Image.new_from_icon_name("non-starred-symbolic", Gtk.IconSize.MENU)
            pin_btn.set_tooltip_text("Pin item (P)")
        pin_btn.set_image(pin_icon)
        pin_btn.connect("clicked", lambda b: self._on_pin_clicked(b, item_id))
        header.pack_start(pin_btn, False, False, 0)

        # 4. Delete button
        del_btn = Gtk.Button()
        del_btn.get_style_context().add_class("clip-action-btn")
        del_btn.get_style_context().add_class("clip-del-btn")
        del_icon = Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.MENU)
        del_btn.set_image(del_icon)
        del_btn.set_tooltip_text("Delete from history (Del)")
        del_btn.connect("clicked", lambda b: self._on_delete_clicked(b, item_id))
        header.pack_start(del_btn, False, False, 0)

        card.pack_start(header, False, False, 0)

        # ==========================================
        # Card Body (Content Preview)
        # ==========================================
        if item_type == "text":
            text_content = item.get("content", "")

            if flavor == "color":
                color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                color_box.get_style_context().add_class("clip-color-box")
                swatch = create_color_swatch_widget(flavor_info)
                if swatch:
                    color_box.pack_start(swatch, False, False, 0)

                hex_lbl = Gtk.Label(label=text_content)
                hex_lbl.get_style_context().add_class("clip-color-hex")
                hex_lbl.set_xalign(0.0)
                color_box.pack_start(hex_lbl, False, False, 0)
                card.pack_start(color_box, False, False, 0)

            elif flavor in ("code", "command"):
                code_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                code_box.get_style_context().add_class("clip-code-box")
                code_lbl = Gtk.Label(label=text_content)
                code_lbl.get_style_context().add_class("clip-code-content")
                code_lbl.set_line_wrap(True)
                code_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                code_lbl.set_lines(4)
                code_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                code_lbl.set_xalign(0.0)
                code_box.pack_start(code_lbl, False, False, 0)
                card.pack_start(code_box, False, False, 0)

            elif flavor == "link":
                url_lbl = Gtk.Label(label=text_content)
                url_lbl.get_style_context().add_class("clip-url-content")
                url_lbl.set_line_wrap(True)
                url_lbl.set_line_wrap_mode(Pango.WrapMode.CHAR)
                url_lbl.set_lines(3)
                url_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                url_lbl.set_xalign(0.0)
                card.pack_start(url_lbl, False, False, 0)

            else:
                preview_lbl = Gtk.Label(label=text_content)
                preview_lbl.get_style_context().add_class("clip-text-content")
                preview_lbl.set_line_wrap(True)
                preview_lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                preview_lbl.set_lines(4)
                preview_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                preview_lbl.set_xalign(0.0)
                card.pack_start(preview_lbl, False, False, 0)

        else:
            # Image card preview
            thumb_path = item.get("thumbnail_path") or item.get("content")
            if thumb_path and os.path.exists(thumb_path):
                img_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                img_box.get_style_context().add_class("clip-image-box")
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        thumb_path, 380, 140, True
                    )
                    image_widget = Gtk.Image.new_from_pixbuf(pixbuf)
                    img_box.pack_start(image_widget, False, False, 0)
                    card.pack_start(img_box, False, False, 0)
                except Exception:
                    pass

        # ==========================================
        # Card Footer (Metadata)
        # ==========================================
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.get_style_context().add_class("clip-footer")

        if item_type == "text":
            chars = item.get("char_count", len(item.get("content", "")))
            lines = item.get("line_count", len(item.get("content", "").splitlines()))
            meta_str = f"{chars} chars • {lines} lines"
        else:
            meta_str = item.get("preview_text", "Image")

        meta_lbl = Gtk.Label(label=meta_str)
        meta_lbl.get_style_context().add_class("clip-meta-badge")
        meta_lbl.set_xalign(0.0)
        footer.pack_start(meta_lbl, False, False, 0)

        card.pack_start(footer, False, False, 0)
        event_box.add(card)

        # Connect click to copy
        event_box.connect("button-release-event", self._on_card_clicked, item)

        return event_box

    def _on_card_clicked(self, widget, event, item: Dict[str, Any]):
        item_type = item.get("item_type", "text")
        content_hash = item.get("content_hash")

        if item_type == "text":
            self.copier.copy_text(item.get("content", ""), content_hash=content_hash)
            self.storage.add_or_touch_text(
                item.get("content", ""),
                item.get("preview_text", ""),
                item.get("char_count", 0),
                item.get("line_count", 0),
                content_hash
            )
        else:
            self.copier.copy_image(item.get("content", ""), content_hash=content_hash)
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

    def _on_open_url_clicked(self, button, url: str):
        try:
            webbrowser.open(url)
            self.hide()
        except Exception:
            pass

    def _on_pin_clicked(self, button: Optional[Gtk.Button], item_id: int):
        new_pinned = self.storage.toggle_pin(item_id)
        self.refresh()
        self.show_toast("📌 Pinned to top" if new_pinned else "Unpinned item")

    def _on_delete_clicked(self, button: Optional[Gtk.Button], item_id: int):
        self.storage.delete_item(item_id)
        self.refresh()
        self.show_toast("🗑️ Item deleted")

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

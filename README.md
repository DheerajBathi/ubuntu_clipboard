# Windows Clipboard for Ubuntu (Win+V) 📋🖼️

A native, lightweight, Windows 11 Fluent-style Clipboard Manager for Ubuntu (GNOME / Wayland & X11) accessible with the **`Super + V`** shortcut key.

It preserves both copied **text** (multi-line, code snippets, links) and **images** (screenshots, copied pictures) in a sleek floating flyout with instant search, pinning, filtering, and single-click copy/paste.

---

## ✨ Features

- ⌨️ **Native `Super + V` Shortcut**: Opens and toggles the clipboard history just like Windows 11.
- 📋 **Full Text Support**: Stores plain text, multi-line snippets, code, URLs, and JSON with line & character counts.
- 🖼️ **Full Image Support**: Captures screenshots (PrintScreen), copied images from browsers, GIMP, etc., with thumbnail previews and dimension metadata.
- 🎨 **Windows 11 Fluent Acrylic Design**: Translucent dark acrylic theme with rounded corners, smooth elevation, glassmorphism, and Libadwaita / GTK styling.
- 💡 **Smart Content Badging**:
  - 🎨 **Live Color Previews**: Hex/RGB codes (`#0078d4`, `rgb(...)`) display real-time rendered color swatch previews.
  - 🔗 **Smart Links**: URLs display domain badges and a one-click "Open in Browser" action button.
  - `< / >` **Code & Commands**: Multi-line snippets and terminal commands render with monospace fonts and code badges.
- 📌 **Pinning**: Pin favorite or frequently used items so they stay permanently and survive clearing.
- 🔍 **Instant Search**: Real-time filtering by keyword or content as you type.
- 🗂️ **Category Tabs with Live Counters**: Filter between **All**, **Text**, **Links**, **Images**, and **Pinned** with real-time count badges.
- 🎯 **Full Keyboard Navigation**: Navigate with `↑`/`↓` arrows, press `Enter` to copy, `P` to pin, and `Delete` to delete.
- 🍞 **Action Toasts**: Instant visual feedback on copy, pin, delete, and clear.
- 🧹 **Clear All**: One-click wipe of unpinned items to keep your clipboard clean.
- ⚡ **Ultra-Fast & Zero CPU Overhead**: Event-based daemon with negligible CPU (<0.01%) and instant response (<15ms) via local IPC.
- 🚀 **Autostart**: Automatically starts on user login.

---

## 🚀 Quick Setup & Installation

Run the setup script from the project directory:

```bash
cd "/home/dheeraj/Desktop/Personal Projects/clipboard"
./setup.sh
```

The script will automatically:
1. Link `winclip` to `~/.local/bin/winclip`.
2. Install the desktop launcher (`.desktop`) and autostart service.
3. Configure Ubuntu's global shortcut **`Super + V`** (Windows key + V) to toggle the clipboard.
4. Launch the background monitoring daemon.

---

## ⌨️ Shortcuts & Navigation

| Key / Action | Description |
| :--- | :--- |
| **`Super + V`** | Toggle the Windows Clipboard flyout open/closed |
| **`↑ / ↓ Arrows`** | Navigate through clipboard items with glowing focus ring |
| **`Enter`** | Copy selected item to clipboard and close flyout |
| **`Click Card`** | Copy item to system clipboard and close flyout |
| **`P` or `📌 Pin`** | Pin/unpin item to keep it permanently at the top |
| **`Del` or `🗑️ Delete`** | Remove individual item from history |
| **`O` or `🔗 Open`** | Open link in default web browser |
| **`Esc`** | Close clipboard flyout |
| **`Click Outside`** | Auto-dismiss flyout (Windows behavior) |

---

## 🛠️ CLI Usage

You can also control the clipboard manager directly from the terminal using `winclip`:

```bash
# Toggle popup window
winclip --toggle

# Check if daemon is active
winclip --status

# Clear all unpinned items
winclip --clear

# Stop daemon
winclip --stop

# Start daemon in background
winclip --daemon
```

---

## 📂 Project Architecture

```
clipboard/
├── bin/
│   └── winclip                  # Executable CLI wrapper
├── winclip/
│   ├── app.py                  # Main GTK4 / Libadwaita coordinator
│   ├── config.py               # Paths, storage limits, and UI dimensions
│   ├── copier.py               # System clipboard writer (wl-copy / xclip)
│   ├── ipc.py                  # Unix Domain Socket server & client
│   ├── monitor.py              # Background clipboard listener (text & images)
│   ├── storage.py              # SQLite storage & thumbnail manager
│   └── ui.py                   # Windows 11 Fluent GUI layout & cards
├── assets/
│   ├── icon.svg                # Application icon
│   └── style.css               # Windows 11 Acrylic dark theme
├── desktop/
│   ├── winclip.desktop         # App launcher entry
│   └── winclip-autostart.desktop # Auto-start entry on login
├── tests/
│   ├── test_monitor.py         # Unit tests for image processing & monitor
│   └── test_storage.py         # Unit tests for storage, pins & search
├── setup.sh                    # Automated installer & shortcut binder
└── README.md                   # Documentation
```

---

## 📦 Storage Locations

- **Database**: `~/.local/share/winclip/clipboard.db`
- **Cached Images**: `~/.local/share/winclip/images/`
- **Thumbnails**: `~/.local/share/winclip/images/thumbs/`
- **Socket**: `~/.local/share/winclip/winclip.sock`
# ubuntu_clipboard

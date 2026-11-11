#!/usr/bin/env bash
# Setup and installation script for Windows Clipboard on Ubuntu

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_PATH="${SCRIPT_DIR}/bin/winclip"
DESKTOP_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"
LOCAL_BIN_DIR="${HOME}/.local/bin"

echo "=========================================================="
echo "  Setting up Windows 11-style Clipboard Manager for Ubuntu"
echo "=========================================================="

# 1. Ensure permissions
chmod +x "${BIN_PATH}" "${SCRIPT_DIR}/main.py"

# 2. Check local directories
mkdir -p "${DESKTOP_DIR}"
mkdir -p "${AUTOSTART_DIR}"
mkdir -p "${LOCAL_BIN_DIR}"

# 3. Create symlink in ~/.local/bin
echo "[1/5] Linking winclip to ${LOCAL_BIN_DIR}/winclip..."
ln -sf "${BIN_PATH}" "${LOCAL_BIN_DIR}/winclip"

# 4. Install Desktop Entry
echo "[2/5] Installing desktop application entry..."
cp "${SCRIPT_DIR}/desktop/winclip.desktop" "${DESKTOP_DIR}/winclip.desktop"
update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true

# 5. Install Autostart Entry
echo "[3/5] Configuring autostart on system login..."
cp "${SCRIPT_DIR}/desktop/winclip-autostart.desktop" "${AUTOSTART_DIR}/winclip.desktop"

# 6. Configure GNOME shortcut for Super+V
echo "[4/5] Configuring global shortcut <Super>v..."

# First: ensure Super+V is freed from toggle-message-tray
gsettings set org.gnome.shell.keybindings toggle-message-tray "['<Super>m']" 2>/dev/null || true

# Next: register custom keybinding for winclip
python3 - << EOF
import subprocess
import ast
import os

KEY_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/winclip/"
SCHEMA = f"org.gnome.settings-daemon.plugins.media-keys.custom-keybinding:{KEY_PATH}"
BIN = os.path.expanduser("~/.local/bin/winclip")

# Set binding parameters
subprocess.run(["gsettings", "set", SCHEMA, "name", "Windows Clipboard"])
subprocess.run(["gsettings", "set", SCHEMA, "command", f"{BIN} --toggle"])
subprocess.run(["gsettings", "set", SCHEMA, "binding", "<Super>v"])

# Add to custom-keybindings list if not already present
raw = subprocess.check_output([
    "gsettings", "get", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings"
]).decode().strip()

try:
    items = ast.literal_eval(raw)
except Exception:
    items = []

if KEY_PATH not in items:
    items.append(KEY_PATH)
    subprocess.run([
        "gsettings", "set", "org.gnome.settings-daemon.plugins.media-keys", "custom-keybindings", str(items)
    ])

print("  Shortcut <Super>v successfully mapped to winclip!")
EOF

# 7. Start the daemon now
echo "[5/5] Starting winclip daemon..."
"${BIN_PATH}" --stop 2>/dev/null || true
"${BIN_PATH}" --daemon &

echo "=========================================================="
echo "  Setup Complete! 🎉"
echo ""
echo "  Try it out:"
echo "  1. Copy some text (Ctrl+C)"
echo "  2. Take a screenshot or copy an image (PrintScreen or Right Click -> Copy Image)"
echo "  3. Press Super+V (Windows key + V) to open your clipboard history!"
echo "=========================================================="

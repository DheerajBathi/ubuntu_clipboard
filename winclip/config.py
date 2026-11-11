"""Configuration and paths for Windows Clipboard for Ubuntu."""
import os
from pathlib import Path

# Base directories
HOME_DIR = Path.home()
DATA_DIR = HOME_DIR / ".local" / "share" / "winclip"
CONFIG_DIR = HOME_DIR / ".config" / "winclip"

# Storage paths
DB_PATH = DATA_DIR / "clipboard.db"
IMAGES_DIR = DATA_DIR / "images"
THUMBS_DIR = IMAGES_DIR / "thumbs"
SOCKET_PATH = DATA_DIR / "winclip.sock"

# Assets path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
CSS_PATH = ASSETS_DIR / "style.css"
ICON_PATH = ASSETS_DIR / "icon.svg"

# Limits & performance settings
MAX_ITEMS = 500
POLL_INTERVAL_SECONDS = 0.40
THUMBNAIL_MAX_SIZE = (360, 180)
JPEG_QUALITY = 85

# UI Settings
WINDOW_WIDTH = 460
WINDOW_HEIGHT = 660
AUTO_HIDE_ON_BLUR = True  # Auto close when clicking outside, like Windows Win+V

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

#!/usr/bin/env python3
"""Prepare the Galadriel desktop application icon assets from one PNG source.

The Desktop app uses several icon files depending on the runtime layer:
- assets/icon.ico: Windows executable/taskbar icon, also copied to resources.
- assets/icon.icns: macOS app bundle icon.
- assets/icon.png: electron-builder/Linux source icon.
- public/apple-touch-icon.png: dev/runtime BrowserWindow icon and favicon.

Usage:
    python apps/desktop/scripts/generate-galadriel-icons.py <source.png>

If no source is passed, the script looks for the generated Imagen source at the
Galadriel Companion root: C:/Users/scorp/.../GaladrielCompanionApp/icon.png.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image

DESKTOP_ROOT = Path(__file__).resolve().parents[1]
COMPANION_ROOT = DESKTOP_ROOT.parents[3]
DEFAULT_SOURCE = COMPANION_ROOT / "icon.png"
CANONICAL_SOURCE = COMPANION_ROOT / "hermes_core" / "home" / "galadriel" / "avatar-assets" / "app-icon-galadriel-source.png"
PNG_PATH = DESKTOP_ROOT / "assets" / "icon.png"
ICO_PATH = DESKTOP_ROOT / "assets" / "icon.ico"
ICNS_PATH = DESKTOP_ROOT / "assets" / "icon.icns"
WEB_ICON_PATH = DESKTOP_ROOT / "public" / "apple-touch-icon.png"
SIZE = 1024
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
ICNS_SIZES = [(16, 16), (32, 32), (128, 128), (256, 256), (512, 512), (1024, 1024)]


def normalize_source(source: Path) -> Image.Image:
    with Image.open(source) as im:
        rgba = im.convert("RGBA")
    if rgba.width != rgba.height:
        side = min(rgba.width, rgba.height)
        left = (rgba.width - side) // 2
        top = (rgba.height - side) // 2
        rgba = rgba.crop((left, top, left + side, top + side))
    return rgba.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def save_icon_assets(source: Path) -> None:
    icon = normalize_source(source)
    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANONICAL_SOURCE.parent.mkdir(parents=True, exist_ok=True)

    icon.save(PNG_PATH, "PNG", optimize=True)
    icon.save(WEB_ICON_PATH, "PNG", optimize=True)
    icon.save(ICO_PATH, "ICO", sizes=ICO_SIZES)
    icon.save(ICNS_PATH, "ICNS", sizes=ICNS_SIZES)
    shutil.copy2(source, CANONICAL_SOURCE)


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    source = source.expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Galadriel icon source not found: {source}")
    save_icon_assets(source)
    print(f"Source: {source}")
    print(f"Canonical source copy: {CANONICAL_SOURCE}")
    print(f"Desktop PNG: {PNG_PATH}")
    print(f"Windows ICO: {ICO_PATH}")
    print(f"macOS ICNS: {ICNS_PATH}")
    print(f"Web/dev icon: {WEB_ICON_PATH}")


if __name__ == "__main__":
    main()

"""
Build-time script: converts gible_joyous.png → icon.png (tray) + icon.ico (exe)
Run this before PyInstaller so the assets exist to bundle.
"""

import os
import sys

from PIL import Image

SRC = os.path.join(os.path.dirname(__file__), "gible_joyous.png")
OUT_PNG = os.path.join(os.path.dirname(__file__), "icon.png")
OUT_ICO = os.path.join(os.path.dirname(__file__), "icon.ico")

src = Image.open(SRC).convert("RGBA")
print(f"Source: {src.size[0]}×{src.size[1]} px RGBA")

# icon.png — 64×64 for the system tray
tray = src.resize((64, 64), Image.LANCZOS)
tray.save(OUT_PNG)
print(f"Wrote {OUT_PNG} (64×64)")

# icon.ico — full size set for exe/taskbar
ico_sizes = [16, 32, 48, 64, 128, 256]
images = [src.resize((s, s), Image.LANCZOS) for s in ico_sizes]
images[0].save(OUT_ICO, format="ICO", sizes=[(s, s) for s in ico_sizes],
               append_images=images[1:])
print(f"Wrote {OUT_ICO} ({', '.join(str(s) for s in ico_sizes)} px)")

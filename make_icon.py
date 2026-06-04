"""
Build-time script: converts lol-to-youtube-icon.svg → icon.png + icon.ico
Run this before PyInstaller so the assets exist to bundle.
"""

import io
import os
import sys

from PIL import Image
from reportlab.graphics import renderPM
from svglib.svglib import svg2rlg

SVG = os.path.join(os.path.dirname(__file__), "lol-to-youtube-icon.svg")
OUT_PNG = os.path.join(os.path.dirname(__file__), "icon.png")
OUT_ICO = os.path.join(os.path.dirname(__file__), "icon.ico")

drawing = svg2rlg(SVG)
if drawing is None:
    print("ERROR: could not parse SVG", file=sys.stderr)
    sys.exit(1)

buf = io.BytesIO()
renderPM.drawToFile(drawing, buf, fmt="PNG", dpi=72)
buf.seek(0)
src = Image.open(buf).convert("RGBA")

src.save(OUT_PNG)
print(f"Wrote {OUT_PNG}")

ico_sizes = [16, 32, 48, 64, 128, 256]
images = [src.resize((s, s), Image.LANCZOS) for s in ico_sizes]
images[0].save(OUT_ICO, format="ICO", sizes=[(s, s) for s in ico_sizes],
               append_images=images[1:])
print(f"Wrote {OUT_ICO}")

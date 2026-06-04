"""
Packages the built exe + config example + README into a release zip.
Run after `make build` or via `make release`.
"""

import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
EXE = os.path.join(ROOT, "dist", "autouploader.exe")
OUT_ZIP = os.path.join(ROOT, "lol-autouploader.zip")

FILES = {
    EXE:                                          "autouploader.exe",
    os.path.join(ROOT, "config.example.json"):   "config.example.json",
    os.path.join(ROOT, "README.md"):             "README.md",
}

for src in FILES:
    if not os.path.exists(src):
        print(f"ERROR: missing {src}", file=sys.stderr)
        sys.exit(1)

# Safety check: make sure no sensitive files sneak in
BANNED = ["config.json", "client_secrets.json", "token.pickle", "uploads.db"]
for name in BANNED:
    if name in FILES.values():
        print(f"ERROR: refusing to include {name} in release", file=sys.stderr)
        sys.exit(1)

if os.path.exists(OUT_ZIP):
    os.remove(OUT_ZIP)

with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for src, arcname in FILES.items():
        zf.write(src, arcname)
        print(f"  + {arcname}")

size_mb = os.path.getsize(OUT_ZIP) / 1024 / 1024
print(f"\nRelease package ready: lol-autouploader.zip ({size_mb:.1f} MB)")

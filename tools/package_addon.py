"""Build the installable Blender extension zip.

    python tools/package_addon.py [dist]   ->  dist/expressnode-<version>.zip

The zip is the `expressnode` package itself, with blender_manifest.toml at its
root, which is the layout Blender's Extensions expect (Preferences › Get
Extensions › Install from Disk). It produces the same layout as
`blender --command extension build --source-dir expressnode`, without needing
Blender, so it can be tested headlessly.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

PKG_NAME = "expressnode"
_SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def _source() -> Path:
    return Path(__file__).resolve().parents[1] / PKG_NAME


def version() -> str:
    text = (_source() / "blender_manifest.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if not m:
        raise ValueError("blender_manifest.toml has no version")
    return m.group(1)


def build(dest_dir: str | Path) -> Path:
    """Zip the extension into dest_dir. Returns the zip path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = _source()
    zip_path = dest_dir / f"{PKG_NAME}-{version()}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            rel = p.relative_to(src)
            if not p.is_file() or _SKIP_DIRS & set(rel.parts) or p.suffix in (".pyc", ".zip"):
                continue
            zf.write(p, rel.as_posix())
    return zip_path


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "dist"
    print(f"built {build(out)}")

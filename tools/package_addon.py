"""Build an installable Blender addon zip.

The IR (formerly sacred_geometry.ir) is vendored inside coding_nodes/_ir,
so the zip only needs to bundle coding_nodes — no sibling repo required.

Resulting zip layout (what Blender's "Install from Disk" expects — a
single top-level package directory):

    coding_nodes_addon/
        __init__.py        (bl_info + register/unregister shim)
        coding_nodes/      (copied, includes _ir/)

`build()` is pure filesystem work — headlessly testable. Whether Blender
loads the result is the M5 Blender checklist step.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

PKG_NAME = "coding_nodes_addon"

_SHIM = '''\
"""ExpressNode — Modifier + Node Group (bundled addon)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

bl_info = {
    "name": "ExpressNode",
    "author": "Geonodes Annihilation",
    "version": (0, 6, 0),
    "blender": (5, 0, 0),
    "location": "Properties > Modifiers · Node Editor > ExpressNode",
    "description": "Compile a Python expression into a Geometry Nodes subtree",
    "category": "Node",
}


def register():
    from coding_nodes.backend import modifier, node_group
    modifier.register()
    node_group.register()


def unregister():
    from coding_nodes.backend import modifier, node_group
    node_group.unregister()
    modifier.unregister()
'''


def _coding_nodes_root() -> Path:
    return Path(__file__).resolve().parents[1]


def build(dest_dir: str | Path) -> Path:
    """Assemble the addon under dest_dir and zip it. Returns the zip path."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stage = dest_dir / PKG_NAME
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    (stage / "__init__.py").write_text(_SHIM, encoding="utf-8")

    def _ignore(_d, names):
        return [n for n in names
                if n in ("__pycache__", ".pytest_cache") or n.endswith(".pyc")]

    shutil.copytree(_coding_nodes_root() / "coding_nodes",
                    stage / "coding_nodes", ignore=_ignore)

    zip_path = dest_dir / f"{PKG_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(dest_dir))
    return zip_path


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "dist"
    z = build(out)
    print(f"built {z}")

"""The packager produces a valid Blender extension zip: the expressnode package
with blender_manifest.toml at the zip root."""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import package_addon  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def test_build_produces_a_versioned_zip(tmp_path):
    z = package_addon.build(tmp_path)
    assert z.exists()
    assert z.name == f"expressnode-{package_addon.version()}.zip"


def test_zip_is_an_extension_with_the_whole_package(tmp_path):
    z = package_addon.build(tmp_path)
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert "blender_manifest.toml" in names
    assert "__init__.py" in names
    for path in ("backend/modifier.py", "backend/node_group.py", "migrate.py",
                 "_ir/__init__.py", "_ir/eval_graph.py"):
        assert path in names, path


def test_manifest_matches_the_package(tmp_path):
    z = package_addon.build(tmp_path)
    with zipfile.ZipFile(z) as zf:
        manifest = zf.read("blender_manifest.toml").decode()
        init = zf.read("__init__.py").decode()
    assert 'id = "expressnode"' in manifest
    assert 'SPDX:GPL-3.0-or-later' in manifest
    assert 'blender_version_min = "5.0.0"' in manifest
    tagline = next(line for line in manifest.splitlines() if line.startswith("tagline"))
    assert len(tagline.split("=", 1)[1].strip().strip('"')) <= 64
    assert "def register()" in init and "def unregister()" in init
    import expressnode
    assert f'version = "{expressnode.__version__}"' in manifest, \
        "manifest and package versions differ"


def test_package_imports_are_relative():
    """Installed, the package is bl_ext.<repo>.expressnode: no module may import
    itself by the plain name."""
    for f in (REPO / "expressnode").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert "from expressnode" not in text and "import expressnode" not in text, f


def test_no_pycache_bundled(tmp_path):
    z = package_addon.build(tmp_path)
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)


def test_rebuild_is_idempotent(tmp_path):
    a = package_addon.build(tmp_path)
    b = package_addon.build(tmp_path)
    assert a == b and b.exists()

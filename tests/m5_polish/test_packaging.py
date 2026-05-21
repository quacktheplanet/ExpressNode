"""The addon packager produces a structurally valid, self-contained
Blender addon zip (bundles both packages + a register shim)."""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import package_addon  # noqa: E402


def test_build_produces_a_zip(tmp_path):
    z = package_addon.build(tmp_path)
    assert z.exists()
    assert z.suffix == ".zip"


def test_zip_contains_both_packages_and_shim(tmp_path):
    z = package_addon.build(tmp_path)
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    p = package_addon.PKG_NAME
    assert f"{p}/__init__.py" in names
    assert f"{p}/coding_nodes/__init__.py" in names
    assert f"{p}/coding_nodes/backend/modifier.py" in names
    assert f"{p}/coding_nodes/backend/node_group.py" in names
    # IR is now vendored inside coding_nodes/_ir (Strategy B split)
    assert f"{p}/coding_nodes/_ir/__init__.py" in names
    assert f"{p}/coding_nodes/_ir/eval_graph.py" in names


def test_shim_has_bl_info_and_registers_both_shapes(tmp_path):
    z = package_addon.build(tmp_path)
    with zipfile.ZipFile(z) as zf:
        shim = zf.read(f"{package_addon.PKG_NAME}/__init__.py").decode()
    assert "bl_info" in shim
    assert "modifier.register()" in shim
    assert "node_group.register()" in shim


def test_no_pycache_bundled(tmp_path):
    z = package_addon.build(tmp_path)
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)


def test_rebuild_is_idempotent(tmp_path):
    a = package_addon.build(tmp_path)
    b = package_addon.build(tmp_path)
    assert a == b and b.exists()

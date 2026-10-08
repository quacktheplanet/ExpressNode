"""Bring files saved with the old add-on (Coding Nodes / Expression Nodes, package
`coding_nodes`) up to date when they are opened.

Generated node trees are ordinary Geometry Nodes, so old files always load and
render. What the old add-on stored under its own names is copied to the new ones:

    object   coding_nodes_expression / _apply_mode / _error  ->  expressnode_*
    scene    coding_nodes_group_expression / _group_error    ->  expressnode_*
    trees    "coding_nodes_params", "coding_nodes_source"     ->  "expressnode_*"
    modifier "CodingNodesExpression"                          ->  "ExpressNode"

The old values are removed after copying, so a file is migrated once. Nothing
else needs migrating: operator ids are not stored in .blend files.
"""

from __future__ import annotations

OLD = "coding" + "_nodes_"          # spelled out so a project-wide rename can't touch it
NEW = "expressnode_"

OBJECT_KEYS = ("expression", "apply_mode", "error")
SCENE_KEYS = ("group_expression", "group_error")
TREE_KEYS = ("params", "source")
OLD_MODIFIER = "Coding" + "NodesExpression"
NEW_MODIFIER = "ExpressNode"


def _stores(id_block):
    """The places an add-on's values live: registered properties are kept in the
    block's system properties (Blender 5.0+), dict-style values in its own."""
    stores = [id_block]
    getter = getattr(id_block, "bl_system_properties_get", None)
    if getter is not None:
        system = getter(do_create=True)
        if system is not None:
            stores.insert(0, system)
    return stores


def _move_idprop(id_block, suffix):
    """Copy an old value to the new name (if the new one is unset), in whichever
    store it was saved in, then remove the old one."""
    old, new = OLD + suffix, NEW + suffix
    moved = False
    for store in _stores(id_block):
        if old not in store.keys():
            continue
        value = store[old]
        if new not in store.keys():
            store[new] = value
        del store[old]
        moved = True
    return moved


def migrate_data(data) -> int:
    """Migrate every block in `data` (bpy.data). Returns how many values moved."""
    moved = 0
    for obj in data.objects:
        for key in OBJECT_KEYS:
            moved += _move_idprop(obj, key)
        mod = obj.modifiers.get(OLD_MODIFIER)
        if mod is not None and obj.modifiers.get(NEW_MODIFIER) is None:
            mod.name = NEW_MODIFIER
            moved += 1
    for scene in data.scenes:
        for key in SCENE_KEYS:
            moved += _move_idprop(scene, key)
    for tree in data.node_groups:
        for key in TREE_KEYS:
            moved += _move_idprop(tree, key)
    return moved


try:                                   # bpy only exists inside Blender
    from bpy.app.handlers import persistent
except ImportError:                    # pragma: no cover - headless tests
    def persistent(fn):
        return fn


@persistent                            # survive file loads, or it would only see the first file
def _on_load(*_args):
    import bpy
    n = migrate_data(bpy.data)
    if n:
        print(f"ExpressNode: brought {n} value(s) from the old add-on's names up to date")


def register():
    import bpy
    if _on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load)


def unregister():
    import bpy
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)

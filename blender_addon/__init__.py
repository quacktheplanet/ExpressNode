"""Expression Nodes — Blender addon shell.

Registers the Expression Modifier and the Expression Node Group. The
engine package (coding_nodes, with its IR vendored in coding_nodes._ir)
must be importable; this puts the repo root on sys.path so the shell
works when linked into Blender's addons folder. The packaged zip
(tools/package_addon.py) bundles the package instead.
"""

import sys
from pathlib import Path

bl_info = {
    "name": "Expression Nodes",
    "author": "Geonodes Annihilation",
    "version": (0, 6, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Modifiers · Node Editor > Expression Nodes",
    "description": "Compile a Python expression into a Geometry Nodes subtree",
    "category": "Node",
}

_CODING_NODES = Path(__file__).resolve().parent.parent
if str(_CODING_NODES) not in sys.path:
    sys.path.insert(0, str(_CODING_NODES))


def register():
    from coding_nodes.backend import modifier
    modifier.register()
    from coding_nodes.backend import node_group
    node_group.register()


def unregister():
    from coding_nodes.backend import node_group
    node_group.unregister()
    from coding_nodes.backend import modifier
    modifier.unregister()


if __name__ == "__main__":
    register()

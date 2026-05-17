"""Coding Nodes — Blender addon shell.

Registers the Expression Modifier. The engine package (coding_nodes) and
its sibling (sacred_geometry) must be importable; this inserts their
parent directories on sys.path so the addon works when dropped into
Blender's addons folder.
"""

import sys
from pathlib import Path

bl_info = {
    "name": "Coding Nodes — Expression Modifier",
    "author": "Geonodes Annihilation",
    "version": (0, 3, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Modifiers > Coding Nodes Expression",
    "description": "Compile a Python expression into a Geometry Nodes subtree",
    "category": "Node",
}

_CODING_NODES = Path(__file__).resolve().parent.parent
_SACRED = _CODING_NODES.parent / "sacred-geometry-engine"
for _p in (_CODING_NODES, _SACRED):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def register():
    from coding_nodes.backend import modifier
    modifier.register()


def unregister():
    from coding_nodes.backend import modifier
    modifier.unregister()


if __name__ == "__main__":
    register()

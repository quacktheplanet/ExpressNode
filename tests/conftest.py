"""Add coding_nodes and sacred_geometry to sys.path so tests can import them
without an install step."""

import sys
from pathlib import Path

_CODING_NODES = Path(__file__).resolve().parent.parent
_SACRED_GEOMETRY = _CODING_NODES.parent / "sacred-geometry-engine"

for p in (_CODING_NODES, _SACRED_GEOMETRY):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

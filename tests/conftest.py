"""Add expressnode to sys.path so tests can import it without an install step.

The IR (formerly sacred_geometry.ir) is now vendored at expressnode._ir,
so no sibling repo path is needed.
"""

import sys
from pathlib import Path

_CODING_NODES = Path(__file__).resolve().parent.parent
if str(_CODING_NODES) not in sys.path:
    sys.path.insert(0, str(_CODING_NODES))

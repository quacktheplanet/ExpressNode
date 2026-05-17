"""If an OSL compiler is on PATH, the generated shaders must compile.
Skips cleanly when oslc is absent (the common headless case) — it then
runs automatically in any environment that does have the toolchain."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from coding_nodes import osl_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
OSLC = shutil.which("oslc")

pytestmark = pytest.mark.skipif(
    OSLC is None, reason="oslc not on PATH (OSL-runtime checklist item)"
)


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_generated_osl_compiles(example):
    src = osl_source((EXAMPLES / example).read_text())
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "shader.osl"
        f.write_text(src)
        r = subprocess.run([OSLC, str(f)], cwd=d,
                            capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

"""If glslangValidator is on PATH, the generated fragment shaders must
compile. Skips cleanly otherwise (the common headless case); auto-runs
wherever the toolchain exists."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from expressnode import glsl_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
GLSLANG = shutil.which("glslangValidator") or shutil.which("glslang")

pytestmark = pytest.mark.skipif(
    GLSLANG is None,
    reason="glslangValidator not on PATH (GLSL-runtime checklist item)",
)


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_generated_glsl_compiles(example):
    src = glsl_source((EXAMPLES / example).read_text())
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "shader.frag"
        f.write_text(src)
        r = subprocess.run([GLSLANG, str(f)],
                            capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

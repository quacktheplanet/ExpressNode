"""If a WGSL validator (naga / tint) is on PATH, the generated compute
shaders must validate. Skips cleanly otherwise; auto-runs wherever the
toolchain exists."""

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from expressnode import wgsl_source

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
NAGA = shutil.which("naga")
TINT = shutil.which("tint")

pytestmark = pytest.mark.skipif(
    NAGA is None and TINT is None,
    reason="no WGSL validator (naga/tint) on PATH (GPU-runtime checklist)",
)


@pytest.mark.parametrize("example", ["ripple.py", "curl_noise.py"])
def test_generated_wgsl_validates(example):
    src = wgsl_source((EXAMPLES / example).read_text())
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "shader.wgsl"
        f.write_text(src)
        cmd = ([NAGA, str(f)] if NAGA else [TINT, str(f)])
        r = subprocess.run(cmd, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr

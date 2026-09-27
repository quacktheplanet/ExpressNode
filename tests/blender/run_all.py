"""Run every Blender and GPU check, on every Blender you point it at.

    python tests/blender/run_all.py --blender "C:/.../Blender 5.1/blender.exe" \\
        --blender "C:/.../blender-5.0.1/blender.exe" [--puppeteer DIR] [--only gn,osl]

Blenders can also come from $EXPN_BLENDERS (paths separated by ';').

Per Blender it runs:
    gn       bl_gn.py        Geometry Nodes parity + M3/M4/M5 checklist   (-b)
    osl      bl_osl.py       OSL compile + Cycles parity                   (-b)
    gui      bl_gui.py       GLSL parity (gpu module) + Shape B in the UI  (small
                             unfocused window; quits by itself)
    install  bl_install.py   packaged zip installs in a throwaway profile  (-b)
and once:
    wgsl     tests/gpu/wgsl_parity.py   WGSL parity + 1M-point dispatch (needs
             Node, puppeteer-core via --puppeteer, Edge/Chrome with WebGPU)

Exit code 0 when every check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]

SCRIPTS = {
    "gn": ("bl_gn.py", True),
    "osl": ("bl_osl.py", True),
    "gui": ("bl_gui.py", False),
    "install": ("bl_install.py", True),
}


def parse(output: str):
    checks, finished = [], False
    for line in output.splitlines():
        if line.startswith("EXPN|"):
            checks.append(json.loads(line[5:]))
        elif line.startswith("EXPN_DONE"):
            finished = True
    return checks, finished


def run_blender(blender, key, zip_path):
    script, background = SCRIPTS[key]
    cmd = [blender]
    if background:
        cmd.append("-b")
    else:
        # The gpu module needs a window: keep it small, in a corner, and
        # don't take focus from whatever the user is doing.
        cmd += ["--no-window-focus", "--window-geometry", "0", "0", "480", "360"]
    cmd += ["--factory-startup", "--python", str(HERE / script)]
    env = dict(os.environ)
    if key == "install":
        sandbox = tempfile.mkdtemp(prefix="expn_profile_")
        env["EXPN_SANDBOX"] = sandbox
        env["BLENDER_USER_RESOURCES"] = sandbox
        cmd += ["--", str(zip_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                              timeout=900, encoding="utf-8", errors="replace")
        out = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        out += "\nTIMEOUT"
    return parse(out) + (out,)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", action="append", default=[])
    ap.add_argument("--puppeteer", default=os.environ.get("PUPPETEER_CORE_DIR"))
    ap.add_argument("--only", default="gn,osl,gui,install,wgsl")
    args = ap.parse_args()
    blenders = args.blender or [
        p for p in os.environ.get("EXPN_BLENDERS", "").split(";") if p]
    only = set(args.only.split(","))
    if not blenders and only - {"wgsl"}:
        ap.error("pass --blender (or set EXPN_BLENDERS)")

    zip_path = None
    if "install" in only:
        sys.path.insert(0, str(REPO / "tools"))
        from package_addon import build
        zip_path = build(pathlib.Path(tempfile.mkdtemp(prefix="expn_dist_")))

    failed = 0
    total = 0
    for blender in blenders:
        for key in ("gn", "osl", "gui", "install"):
            if key not in only:
                continue
            checks, finished, out = run_blender(blender, key, zip_path)
            version = next((c["detail"] for c in checks
                            if c["check"] == "blender version"), "?")
            bad = [c for c in checks if not c["ok"]]
            total += len(checks)
            failed += len(bad) + (0 if finished else 1)
            state = "ok" if finished and not bad else "FAIL"
            print(f"[{state}] Blender {version} {key}: "
                  f"{len(checks) - len(bad)}/{len(checks)} checks"
                  + ("" if finished else "  (script did not finish)"))
            for c in bad:
                print(f"    FAIL {c['check']}: {c['detail'][:300]}")
            if not finished:
                print("    " + out[-1500:].replace("\n", "\n    "))

    if "wgsl" in only:
        cmd = [sys.executable, str(REPO / "tests" / "gpu" / "wgsl_parity.py")]
        if args.puppeteer:
            cmd += ["--puppeteer", args.puppeteer]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        checks, finished = parse(proc.stdout)
        bad = [c for c in checks if not c["ok"]]
        total += len(checks)
        failed += len(bad) + (0 if finished else 1)
        print(f"[{'ok' if finished and not bad else 'FAIL'}] WGSL (WebGPU): "
              f"{len(checks) - len(bad)}/{len(checks)} checks")
        for c in bad:
            print(f"    FAIL {c['check']}: {c['detail'][:300]}")
        if not finished:
            print("    " + (proc.stdout + proc.stderr)[-1500:])

    print(f"\n{total - failed} of {total} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

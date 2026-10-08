"""WGSL backend checks on a real GPU (TESTING.md M9 runtime checklist).

    python tests/gpu/wgsl_parity.py [--puppeteer DIR]

Compiles every WGSL case's kernel with the browser's WebGPU compiler
(checklist item 1, in place of naga/tint), dispatches it over a set of
points and compares out_R with the numpy oracle (items 2 and 3), then
runs ripple over 1,000,000 points in one dispatch (item 4).

Needs Node, puppeteer-core (pass the folder holding its node_modules with
--puppeteer or $PUPPETEER_CORE_DIR) and Edge or Chrome with WebGPU
($BROWSER overrides the Edge path). Prints the same EXPN| lines as the
Blender checks.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO), str(REPO / "tests" / "blender")]

import numpy as np  # noqa: E402

import cases  # noqa: E402
from expressnode import compile as cn_compile, evaluate, wgsl_source  # noqa: E402

_failed = []


def check(name, ok, detail=""):
    ok = bool(ok)
    if not ok:
        _failed.append(name)
    print("EXPN|" + json.dumps({"check": name, "ok": ok,
                                "detail": str(detail)}), flush=True)
    return ok


def uniforms_for(case):
    compiled = cn_compile(case["source"])
    params = case.get("params") or {}
    u = [{"type": "f32", "value": cases.TIME},
         {"type": "f32", "value": float(cases.FRAME)},
         {"type": "f32", "value": 1.0 / cases.FPS},
         {"type": "i32", "value": 0}]
    for p in compiled.parameters:
        u.append({"type": "f32", "value": float(params.get(p.name, p.default))})
    return u


def oracle(case, P):
    v = evaluate(cn_compile(case["source"]), P=P, t=cases.TIME,
                 frame=float(cases.FRAME), dt=1.0 / cases.FPS,
                 params=case.get("params") or None).values
    v = np.asarray(v, dtype=np.float64)
    return np.repeat(v[:, None], 3, axis=1) if v.ndim == 1 else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puppeteer", default=None)
    args = ap.parse_args()

    P = np.array(cases.sample_points(2000, seed=11), dtype=np.float32)
    job = {"cases": []}
    for case in cases.cases_for("wgsl"):
        job["cases"].append({"name": case["name"],
                             "source": wgsl_source(case["source"]),
                             "points": P.ravel().tolist(),
                             "uniforms": uniforms_for(case)})
    ripple = next(c for c in cases.CASES if c["name"] == "ripple")
    big = np.random.default_rng(3).uniform(-2, 2, (1_000_000, 3)).astype(np.float32)
    job["cases"].append({"name": "scale_1M", "source": wgsl_source(ripple["source"]),
                         "points": big.ravel().tolist(),
                         "uniforms": uniforms_for(ripple),
                         "return_count": 2000})

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="expn_wgsl_"))
    (tmp / "job.json").write_text(json.dumps(job), encoding="utf-8")
    cmd = ["node", str(HERE / "wgsl_run.mjs"), str(tmp / "job.json"),
           str(tmp / "out.json")]
    if args.puppeteer:
        cmd.append(args.puppeteer)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not (tmp / "out.json").exists():
        check("wgsl harness ran", False, (proc.stderr or proc.stdout)[-800:])
        print(f"EXPN_DONE failed={len(_failed)}")
        return 1
    out = json.loads((tmp / "out.json").read_text(encoding="utf-8"))
    if "error" in out:
        check("wgsl harness ran", False, out["error"])
        print(f"EXPN_DONE failed={len(_failed)}")
        return 1
    check("webgpu adapter", True, out.get("adapter", ""))

    P64 = P.astype(np.float64)
    for case in cases.cases_for("wgsl"):
        r = out["results"].get(case["name"], {})
        if not check(f"wgsl compile {case['name']}", "error" not in r,
                     r.get("error", "compiled and dispatched by WebGPU")):
            continue
        got = np.array(r["out"], dtype=np.float64).reshape(-1, 3)
        want = oracle(case, P64)

        def retry(i, case=case):
            for axis in range(3):
                for d in (-1e-5, 1e-5):
                    q = P64[i:i + 1].copy()
                    q[0, axis] += d
                    yield oracle(case, q)[0]

        max_err, misses, forgiven = cases.tolerance_check(
            np, got, want, retry, atol=case.get("atol", 2e-4))
        noisy = any(op in case["source"] for op in ("noise(", "voronoi("))
        detail = (f"{len(P)} points, max err {max_err:.2e}, misses {misses}, "
                  f"edge points forgiven {forgiven}")
        if misses:
            err = np.abs(got - want).max(axis=1)
            worst = np.argsort(-err)[:2]
            detail += "; worst: " + "; ".join(
                f"P={np.round(P64[i], 4).tolist()} got={np.round(got[i], 4).tolist()}"
                f" want={np.round(want[i], 4).tolist()}" for i in worst)
        check(f"{'wgsl noise parity' if noisy else 'wgsl parity'} {case['name']}",
              misses == 0, detail)

    r = out["results"].get("scale_1M", {})
    if check("wgsl 1M points in one dispatch", "error" not in r,
             r.get("error", f"{r.get('n', 0):,} points in {r.get('ms', 0):.1f} ms "
                            "(submit to done, incl. first-use pipeline)")):
        got = np.array(r["out"], dtype=np.float64).reshape(-1, 3)
        want = oracle(ripple, big[:len(got)].astype(np.float64))
        check("wgsl 1M results match the oracle (first 2000)",
              np.abs(got - want).max() < 2e-4,
              f"max err {np.abs(got - want).max():.2e}")
    print(f"EXPN_DONE failed={len(_failed)}", flush=True)
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())

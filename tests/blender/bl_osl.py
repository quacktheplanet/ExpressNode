"""OSL backend checks in Cycles (TESTING.md M7 runtime checklist).

    blender -b --factory-startup --python tests/blender/bl_osl.py

For every OSL case: compile the generated shader with Blender's own OSL
compiler, load it into a Cycles Script node, render a tilted plane with
the shader's Result as emission, render again with the shading point's
position as emission, and compare Result with the oracle evaluated at
those exact positions. Both renders use the same seed, so pixel i sees
the same shading point in both. Values are shifted by BIAS so they stay
positive through the film.
"""

from __future__ import annotations

import os
import sys
import pathlib
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import check, done, guard  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import cases  # noqa: E402
from coding_nodes import compile as cn_compile, evaluate, osl_source  # noqa: E402

RES = 48
BIAS = 8.0
TMP = pathlib.Path(tempfile.mkdtemp(prefix="expn_osl_"))


def setup_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    cy = scene.cycles
    cy.device = "CPU"
    cy.shading_system = True
    cy.samples = 1
    cy.use_adaptive_sampling = False
    cy.use_denoising = False
    cy.max_bounces = 0
    cy.sample_clamp_direct = 0.0
    cy.sample_clamp_indirect = 0.0
    cy.pixel_filter_type = "BOX"
    cy.filter_width = 0.01
    scene.render.film_transparent = True
    scene.render.resolution_x = RES
    scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    img = scene.render.image_settings
    img.file_format = "OPEN_EXR"
    img.color_depth = "32"
    img.exr_codec = "NONE"
    img.color_mode = "RGBA"

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 3.4
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.0, 0.0, 5.0)
    scene.collection.objects.link(cam)
    scene.camera = cam

    bpy.ops.mesh.primitive_plane_add(size=4.0, rotation=(0.35, -0.25, 0.0))
    plane = bpy.context.active_object
    mat = bpy.data.materials.new("Expr")
    mat.use_nodes = True
    plane.data.materials.append(mat)
    return scene, mat


def compile_script(mat, source):
    text = bpy.data.texts.new("expr.osl")
    text.from_string(source)
    nt = mat.node_tree
    nt.nodes.clear()
    script = nt.nodes.new("ShaderNodeScript")
    script.mode = "INTERNAL"
    script.script = text
    import cycles.osl as cosl
    messages = []
    ok = cosl.update_script_node(
        script, lambda kind, msg: messages.append(f"{kind}: {msg}"))
    ok = ok is not False and "Result" in script.outputs
    return script, ok, "; ".join(str(m) for m in messages)


def emit(mat, socket):
    nt = mat.node_tree
    for n in [n for n in nt.nodes if n.bl_idname != "ShaderNodeScript"]:
        nt.nodes.remove(n)
    add = nt.nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    add.inputs[1].default_value = (BIAS, BIAS, BIAS)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if socket == "position":
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        socket = geo.outputs["Position"]
    nt.links.new(socket, add.inputs[0])
    nt.links.new(add.outputs[0], em.inputs["Color"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])


def render(path):
    scene = bpy.context.scene
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path))
    img.colorspace_settings.name = "Non-Color"
    px = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(-1, 4)


def osl_case(mat, case):
    name = case["name"]
    src = osl_source(case["source"])
    script, ok, msg = compile_script(mat, src)
    if not check(f"osl compile {name}", ok, msg or "compiled by Cycles"):
        return
    script.inputs["Time"].default_value = cases.TIME
    script.inputs["Frame"].default_value = float(cases.FRAME)
    for k, v in (case.get("params") or {}).items():
        script.inputs[k].default_value = v

    emit(mat, "position")
    pos = render(TMP / f"{name}_P.exr")
    emit(mat, script.outputs["Result"])
    res = render(TMP / f"{name}_R.exr")

    mask = pos[:, 3] > 0.999
    P = pos[mask, :3].astype(np.float64) - BIAS
    got = res[mask, :3].astype(np.float64) - BIAS
    compiled = cn_compile(case["source"])

    def oracle(q):
        v = evaluate(compiled, P=q, t=cases.TIME, frame=float(cases.FRAME),
                     params=case.get("params") or None).values
        v = np.asarray(v, dtype=np.float64)
        return np.repeat(v[:, None], 3, axis=1) if v.ndim == 1 else v

    want = oracle(P)

    def retry(i):
        for axis in range(3):
            for d in (-1e-5, 1e-5):
                q = P[i:i + 1].copy()
                q[0, axis] += d
                yield oracle(q)[0]

    max_err, misses, forgiven = cases.tolerance_check(
        np, got, want, retry, atol=case.get("atol", 2e-4))
    detail = (f"{len(P)} shading points, max err {max_err:.2e}, misses "
              f"{misses}, edge points forgiven {forgiven}")
    if misses:
        err = np.abs(got - want).max(axis=1)
        worst = np.argsort(-err)[:2]
        detail += "; worst: " + "; ".join(
            f"P={np.round(P[i], 4).tolist()} got={np.round(got[i], 4).tolist()}"
            f" want={np.round(want[i], 4).tolist()}" for i in worst)
    noisy = any(op in case["source"] for op in ("noise(", "voronoi("))
    label = "osl noise parity" if noisy else "osl parity"
    check(f"{label} {name}", misses == 0 and len(P) > RES * RES // 3, detail)


def standalone_compile():
    """Checklist item 1: the generated .osl compiles with oslc (Blender's
    bundled compiler, through the Cycles module)."""
    import _cycles
    for case in cases.cases_for("osl"):
        src = TMP / f"{case['name']}.osl"
        src.write_text(osl_source(case["source"]), encoding="utf-8")
        oso = TMP / f"{case['name']}.oso"
        ok = _cycles.osl_compile(str(src), str(oso))
        check(f"oslc {case['name']}", ok and oso.exists(), str(oso.name))


def main():
    guard("oslc", standalone_compile)
    scene, mat = setup_scene()
    for case in cases.cases_for("osl"):
        guard(f"osl parity {case['name']}", osl_case, mat, case)
    check("blender version", True, bpy.app.version_string)
    done()


main()

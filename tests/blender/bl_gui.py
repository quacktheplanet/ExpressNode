"""Checks that need a Blender window (TESTING.md M4 and M8).

    blender --factory-startup --python tests/blender/bl_gui.py

(no -b: the gpu module and the editors need a window). Quits by itself.

- GLSL: every GLSL case's generated function is compiled by Blender's gpu
  module and run over a float offscreen buffer; one pass writes the
  position each pixel used, one writes the Result, and the Result is
  compared with the oracle at those positions.
- Shape B: the Add / Update Expression Group operators run in a real
  Node Editor, and the ExpressNode panels draw without errors in
  the Node Editor sidebar and the modifier properties.
"""

from __future__ import annotations

import sys
import pathlib
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import check, done, guard, register_addon  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import cases  # noqa: E402
from expressnode import compile as cn_compile, evaluate, glsl_source  # noqa: E402

RES = 64

VERT = "void main() { gl_Position = vec4(pos, 0.0, 1.0); }"

# P varies over [-1.5, 1.5] in x and y and non-linearly in z; the pass
# writes P itself (mode 0) or the expression's Result (mode 1).
FRAG_MAIN = """
void main() {
    float ix = gl_FragCoord.x - 0.5;
    float iy = gl_FragCoord.y - 0.5;
    vec3 P = vec3(-1.5 + ix * (3.0 / 63.0), -1.5 + iy * (3.0 / 63.0), 0.0);
    P.z = 0.6 * sin(P.x * 1.7) + 0.4 * P.y;
    vec3 N = vec3(0.0, 0.0, 1.0);
    if (mode == 0) {
        fragColor = vec4(P, 1.0);
    } else {
        fragColor = vec4(CALL, 1.0);
    }
}
"""


def glsl_function(case) -> tuple[str, str]:
    """(library + function source, call expression) from the generated
    shader: its own main() and #version are dropped; we supply ours."""
    src = glsl_source(case["source"])
    body = src.split("out vec4 _fragColor;")[0]
    body = "\n".join(l for l in body.splitlines()
                     if not l.startswith("#version"))
    compiled = cn_compile(case["source"])
    fn = next(l for l in body.splitlines()
              if l.startswith(("vec3 expr_", "float expr_")))
    name = fn.split("(")[0].split()[1]
    params = case.get("params") or {}
    args = ["P", "N", f"{cases.TIME:.6f}", f"{float(cases.FRAME):.6f}",
            f"{1.0 / cases.FPS:.8f}", "0"]
    for p in compiled.parameters:
        v = params.get(p.name, p.default)
        args.append(f"{float(v):.8f}")
    call = f"{name}({', '.join(args)})"
    if fn.startswith("float"):
        call = f"vec3({call})"
    return body, call


def run_shader(body, call):
    import gpu
    from gpu_extras.batch import batch_for_shader
    info = gpu.types.GPUShaderCreateInfo()
    info.vertex_in(0, "VEC2", "pos")
    info.push_constant("INT", "mode")
    info.fragment_out(0, "VEC4", "fragColor")
    info.vertex_source(VERT)
    info.fragment_source(body + FRAG_MAIN.replace("CALL", call))
    shader = gpu.shader.create_from_info(info)
    batch = batch_for_shader(shader, "TRIS", {
        "pos": [(-1, -1), (3, -1), (-1, 3)]})
    off = gpu.types.GPUOffScreen(RES, RES, format="RGBA32F")
    out = []
    for mode in (0, 1):
        with off.bind():
            fb = gpu.state.active_framebuffer_get()
            fb.clear(color=(0.0, 0.0, 0.0, 0.0))
            shader.bind()
            shader.uniform_int("mode", mode)
            batch.draw(shader)
            buf = fb.read_color(0, 0, RES, RES, 4, 0, "FLOAT")
        buf.dimensions = RES * RES * 4
        out.append(np.array(buf, dtype=np.float64).reshape(-1, 4))
    off.free()
    return out


def glsl_case(case):
    name = case["name"]
    body, call = glsl_function(case)
    try:
        pos, res = run_shader(body, call)
    except Exception as e:  # noqa: BLE001
        check(f"glsl compile {name}", False, f"{type(e).__name__}: {e}")
        return
    check(f"glsl compile {name}", True, "compiled by Blender's gpu module")
    P = pos[:, :3]
    got = res[:, :3]
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
    detail = (f"{len(P)} pixels, max err {max_err:.2e}, misses {misses}, "
              f"edge points forgiven {forgiven}")
    if misses:
        err = np.abs(got - want).max(axis=1)
        worst = np.argsort(-err)[:2]
        detail += "; worst: " + "; ".join(
            f"P={np.round(P[i], 4).tolist()} got={np.round(got[i], 4).tolist()}"
            f" want={np.round(want[i], 4).tolist()}" for i in worst)
    noisy = any(op in case["source"] for op in ("noise(", "voronoi("))
    check(f"{'glsl noise parity' if noisy else 'glsl parity'} {name}",
          misses == 0, detail)


# ---------------------------------------------------------------------------
# Shape B in a real Node Editor, panels drawing
# ---------------------------------------------------------------------------

def editor_area(kind):
    win = bpy.context.window_manager.windows[0]
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    area.type = kind
    region = next(r for r in area.regions if r.type == "WINDOW")
    return win, area, region


def shape_b_operators():
    scene = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=2)
    obj = bpy.context.active_object
    host = bpy.data.node_groups.new("Host Tree", "GeometryNodeTree")
    host.interface.new_socket("Geometry", in_out="INPUT",
                              socket_type="NodeSocketGeometry")
    host.interface.new_socket("Geometry", in_out="OUTPUT",
                              socket_type="NodeSocketGeometry")
    host.nodes.new("NodeGroupInput")
    host.nodes.new("NodeGroupOutput")
    mod = obj.modifiers.new("Host", "NODES")
    mod.node_group = host

    win, area, region = editor_area("NODE_EDITOR")
    space = area.spaces.active
    space.tree_type = "GeometryNodeTree"
    space.node_tree = host
    space.show_region_ui = True
    space.cursor_location = (320.0, -40.0)

    with bpy.context.temp_override(window=win, area=area, region=region):
        result = bpy.ops.expressnode.add_expression_group()
    groups = [n for n in host.nodes if n.bl_idname == "GeometryNodeGroup"]
    ok = (result == {"FINISHED"} and len(groups) == 1
          and groups[0].node_tree is not None
          and groups[0].node_tree.name == "Expr_offset")
    check("4.1/4.2 Add Expression Node Group in the Node Editor", ok,
          f"{result}, group nodes {[g.node_tree.name for g in groups if g.node_tree]}")
    if not ok:
        return
    gnode = groups[0]
    check("4.2 new node lands at the editor cursor",
          tuple(round(v) for v in gnode.location) == (320, -40),
          tuple(gnode.location))

    scene.expressnode_group_expression = (
        "def offset(P, t, amp=0.3):\n"
        "    return vec3(amp, 0.0, 0.0)\n")
    with bpy.context.temp_override(window=win, area=area, region=region):
        result = bpy.ops.expressnode.update_expression_group()
    kinds = {n.bl_idname for n in gnode.node_tree.nodes}
    check("Update Selected Group rebuilds the active group",
          result == {"FINISHED"} and gnode.node_tree.name == "Expr_offset"
          and "ShaderNodeMath" not in kinds,
          f"{result}, nodes {sorted(kinds)}")

    scene.expressnode_group_expression = "def f(P):\n    return P +"
    with bpy.context.temp_override(window=win, area=area, region=region):
        result = bpy.ops.expressnode.add_expression_group()
    check("4.4 bad expression: error in panel, no node added",
          result == {"CANCELLED"} and scene.expressnode_group_error
          and len([n for n in host.nodes
                   if n.bl_idname == "GeometryNodeGroup"]) == 1,
          scene.expressnode_group_error.splitlines()[0]
          if scene.expressnode_group_error else "")

    # Panels: draw the Node Editor sidebar tab and the modifier panel.
    ui = next(r for r in area.regions if r.type == "UI")
    try:
        ui.active_panel_category = "ExpressNode"
    except (AttributeError, TypeError):
        pass
    errors = draw_errors()
    check("Node Editor panel draws without errors", not errors,
          errors[:300] or "drawn")

    win, area, region = editor_area("PROPERTIES")
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    area.spaces.active.context = "MODIFIER"
    obj.expressnode_error = "CompileError at line 1: example"
    errors = draw_errors()
    check("modifier panel draws without errors (with an error box)",
          not errors, errors[:300] or "drawn")


_draw_log = []


def draw_errors() -> str:
    """Redraw the window, returning any Python error text a panel's
    draw() printed."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(buf):
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
    text = buf.getvalue()
    return text if ("Traceback" in text or "Error" in text) else ""


def main():
    try:
        register_addon()
        for case in cases.cases_for("glsl"):
            guard(f"glsl {case['name']}", glsl_case, case)
        guard("shape b operators", shape_b_operators)
        import gpu
        check("gpu backend", True, f"{gpu.platform.backend_type_get()} "
              f"{gpu.platform.renderer_get()}")
        check("blender version", True, bpy.app.version_string)
    except Exception:  # noqa: BLE001
        check("bl_gui crashed", False, traceback.format_exc())
    done()
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(main, first_interval=1.5)

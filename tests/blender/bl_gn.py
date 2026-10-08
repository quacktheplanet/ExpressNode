"""Geometry Nodes checks in Blender (TESTING.md M3, M4, M5).

    blender -b --factory-startup --python tests/blender/bl_gn.py

Builds every Geometry Nodes case through the real add-on, evaluates the
modifier on a point cloud and compares the moved points with the numpy
oracle. Also covers the checklist behaviour: registration, the ripple
golden path, compile errors that leave the last good modifier alone,
curl-noise sub-groups, apply modes, parameter values surviving a
recompile, Shape B groups dropped into a tree and rebuilt in place.
"""

from __future__ import annotations

import math
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from common import check, done, guard, register_addon  # noqa: E402

import bpy  # noqa: E402
import numpy as np  # noqa: E402

import cases  # noqa: E402
from expressnode import compile as cn_compile, evaluate  # noqa: E402
from expressnode.backend import modifier as cn_mod  # noqa: E402
from expressnode.backend.pipeline import build_in_blender  # noqa: E402

TARGET = {"position": (0.4, -0.2, 1.1), "scale": (1.5, 0.5, 2.0),
          "rotation": (0.1, 0.2, 0.3)}


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = cases.FPS
    scene.render.fps_base = 1.0
    scene.frame_set(cases.FRAME)
    return scene


def point_object(name="Pts", n=400):
    pts = np.array(cases.sample_points(n), dtype=np.float32)
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(pts))
    mesh.vertices.foreach_set("co", pts.ravel())
    attr = mesh.attributes.new("seed_attr", "FLOAT", "POINT")
    seed = np.sin(np.arange(len(pts)) * 0.37).astype(np.float32)
    attr.data.foreach_set("value", seed)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def sphere_object(name="Sphere"):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12,
                                         radius=1.2)
    obj = bpy.context.active_object
    obj.name = name
    return obj


def target_object():
    obj = bpy.data.objects.new("Target", None)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = TARGET["position"]
    obj.scale = TARGET["scale"]
    obj.rotation_euler = TARGET["rotation"]
    return obj


def activate(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def positions(obj, evaluated=True):
    if evaluated:
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        ob = obj.evaluated_get(dg)
        mesh = ob.to_mesh()
    else:
        mesh = obj.data
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", co)
    out = co.reshape(-1, 3).astype(np.float64)
    if evaluated:
        ob.to_mesh_clear()
    return out


def eval_attribute(obj, name):
    dg = bpy.context.evaluated_depsgraph_get()
    ob = obj.evaluated_get(dg)
    mesh = ob.to_mesh()
    attr = mesh.attributes.get(name)
    vals = None
    if attr is not None:
        vals = np.empty(len(attr.data), dtype=np.float32)
        attr.data.foreach_get("value", vals)
    ob.to_mesh_clear()
    return vals


def set_inputs(mod, values: dict):
    for item in mod.node_group.interface.items_tree:
        if (item.item_type == "SOCKET" and item.in_out == "INPUT"
                and item.name in values):
            cn_mod.set_input(mod, item.identifier, values[item.name])
    mod.id_data.update_tag()


def input_value(mod, name):
    for item in mod.node_group.interface.items_tree:
        if (item.item_type == "SOCKET" and item.in_out == "INPUT"
                and item.name == name):
            return cn_mod.get_input(mod, item.identifier)
    raise KeyError(name)


def expr_tree(mod):
    return next(n.node_tree for n in mod.node_group.nodes
                if n.bl_idname == "GeometryNodeGroup")


def recompile(obj, source, mode="offset"):
    activate(obj)
    obj.expressnode_expression = source
    obj.expressnode_apply_mode = mode
    return bpy.ops.expressnode.recompile()


# ---------------------------------------------------------------------------
# Parity: every Geometry Nodes case against the oracle
# ---------------------------------------------------------------------------

def oracle_for(case, P, normals=None, seed_attr=None, mode="offset"):
    compiled = cn_compile(case["source"])
    res = evaluate(
        compiled, P=P, t=cases.TIME, frame=float(cases.FRAME),
        dt=1.0 / cases.FPS, normals=normals,
        params=case.get("params") or None,
        attributes={"seed_attr": seed_attr} if seed_attr is not None else None,
        objects={"Target": {k: np.array(v) for k, v in TARGET.items()}},
    ).values
    res = np.asarray(res, dtype=np.float64)
    if res.ndim == 1:
        res = np.repeat(res[:, None], 3, axis=1)
    return res


def parity_case(case):
    reset_scene()
    target_object()
    if case["name"] == "builtins":
        obj = sphere_object()
        mesh = obj.data
        normals = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
        mesh.vertex_normals.foreach_get("vector", normals)
        normals = normals.reshape(-1, 3).astype(np.float64)
    else:
        obj = point_object()
        normals = None
    seed_attr = None
    if "seed_attr" in obj.data.attributes:
        seed_attr = np.empty(len(obj.data.vertices), dtype=np.float32)
        obj.data.attributes["seed_attr"].data.foreach_get("value", seed_attr)

    thresh = case.get("inline_threshold")
    if thresh is None:
        result = recompile(obj, case["source"])
        if result != {"FINISHED"}:
            check(f"gn parity {case['name']}", False,
                  f"recompile: {result}: {obj.expressnode_error}")
            return
        mod = obj.modifiers[cn_mod.MODIFIER_NAME]
    else:
        err = cn_mod._apply(obj, case["source"], inline_threshold=thresh)
        if err:
            check(f"gn parity {case['name']}", False, err)
            return
        mod = obj.modifiers[cn_mod.MODIFIER_NAME]
    if case.get("params"):
        set_inputs(mod, case["params"])

    P = positions(obj, evaluated=False)
    got = positions(obj) - P
    want = oracle_for(case, P, normals, seed_attr)

    def retry(i):
        for axis in range(3):
            for d in (-1e-5, 1e-5):
                q = P[i:i + 1].copy()
                q[0, axis] += d
                n = normals[i:i + 1] if normals is not None else None
                sa = seed_attr[i:i + 1] if seed_attr is not None else None
                yield oracle_for(case, q, n, sa)[0]

    max_err, misses, forgiven = cases.tolerance_check(
        np, got, want, retry, atol=case.get("atol", 2e-4))
    groups = sum(1 for n in expr_tree(mod).nodes
                 if n.bl_idname == "GeometryNodeGroup")
    detail = (f"{len(P)} points, max err {max_err:.2e}, misses {misses}, "
              f"edge points forgiven {forgiven}, sub-group nodes {groups}")
    if misses:
        err = np.abs(got - want)
        err[~np.isfinite(err)] = np.inf
        worst = np.argsort(-err.max(axis=1))[:3]
        detail += "; worst: " + "; ".join(
            f"P={np.round(P[i], 4).tolist()} got={np.round(got[i], 4).tolist()}"
            f" want={np.round(want[i], 4).tolist()}" for i in worst)
    check(f"gn parity {case['name']}", misses == 0, detail)

    if case["name"] == "access":
        heat = eval_attribute(obj, "heat")
        ok = heat is not None and np.allclose(heat, P[:, 0] * 2.0, atol=1e-5)
        check("gn set_attr stores the attribute", ok,
              "heat == 2*P.x" if ok else f"heat={heat if heat is None else heat[:4]}")
    if case["name"] == "helper_attr":
        heat = eval_attribute(obj, "heat")
        want = np.sin(P[:, 0] * 1.3) * 0.5 + P[:, 1] * P[:, 2]
        ok = heat is not None and np.allclose(heat, want, atol=1e-5)
        depth = _nesting_depth(expr_tree(mod))
        check("gn set_attr inside nested helpers stores the attribute", ok and depth >= 2,
              f"group nesting depth {depth}, "
              + ("heat matches" if ok else f"heat={heat if heat is None else heat[:4]}"))
    if case["name"] == "helpers":
        depth = _nesting_depth(expr_tree(mod))
        check("gn nested helper groups (2 levels)", depth >= 2,
              f"group nesting depth {depth}")


def _nesting_depth(tree, seen=()):
    best = 0
    for n in tree.nodes:
        if n.bl_idname == "GeometryNodeGroup" and n.node_tree not in seen:
            best = max(best, 1 + _nesting_depth(n.node_tree,
                                                seen + (tree,)))
    return best


# ---------------------------------------------------------------------------
# Checklist behaviour
# ---------------------------------------------------------------------------

def check_registration():
    ok = (hasattr(bpy.ops.expressnode, "recompile")
          and hasattr(bpy.ops.expressnode, "add_expression_group")
          and hasattr(bpy.ops.expressnode, "update_expression_group")
          and hasattr(bpy.types, "EXPRESSNODE_PT_panel")
          and hasattr(bpy.types, "EXPRESSNODE_PT_group_panel"))
    check("3.1 add-on registers operators and panels", ok)


def check_ripple_golden_path():
    reset_scene()
    bpy.ops.mesh.primitive_plane_add(size=4)
    plane = bpy.context.active_object
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=30)
    bpy.ops.object.mode_set(mode="OBJECT")
    src = (cases._EXAMPLES / "ripple.py").read_text(encoding="utf-8")
    result = recompile(plane, src)
    mod = plane.modifiers.get(cn_mod.MODIFIER_NAME)
    ok = result == {"FINISHED"} and mod is not None and mod.type == "NODES"
    check("3.2 ripple builds a Nodes modifier", ok, str(result))
    if not ok:
        return
    tree = expr_tree(mod)
    names = [i.name for i in mod.node_group.interface.items_tree
             if i.item_type == "SOCKET" and i.in_out == "INPUT"]
    check("3.2 group names", tree.name == "Expr_ripple [Plane]"
          and mod.node_group.name == "Modifier_Expr_ripple [Plane]",
          f"{tree.name} / {mod.node_group.name}")
    check("3.2 freq and amp are modifier inputs with their defaults",
          "freq" in names and "amp" in names
          and math.isclose(input_value(mod, "freq"), 6.0)
          and math.isclose(input_value(mod, "amp"), 0.3, rel_tol=1e-6),
          f"inputs {names}")
    kinds = sorted(n.bl_idname for n in tree.nodes)
    check("3.2 readable graph (small, no wall of Math nodes)",
          len(tree.nodes) <= 14, f"{len(tree.nodes)} nodes: {kinds}")

    a = positions(plane)
    bpy.context.scene.frame_set(cases.FRAME + 8)
    b = positions(plane)
    check("3.2 plane ripples and animates with time",
          np.ptp(a[:, 2]) > 0.5 and np.abs(a - b).max() > 0.05,
          f"z range {np.ptp(a[:, 2]):.3f}, frame change moves up to "
          f"{np.abs(a - b).max():.3f}")
    set_inputs(mod, {"freq": 12.0})
    c = positions(plane)
    check("3.2 changing freq changes the waves", np.abs(c - b).max() > 0.05)

    # 3.3 compile error: the last good modifier stays
    before = mod.node_group
    result = recompile(plane, 'def f(): return getattr(math, "sin")(P.x)')
    err = plane.expressnode_error
    check("3.3 compile error is reported, not raised",
          result == {"CANCELLED"} and "line" in err.lower(),
          err.splitlines()[0] if err else "no error text")
    check("3.3 previous modifier intact",
          plane.modifiers.get(cn_mod.MODIFIER_NAME) is not None
          and plane.modifiers[cn_mod.MODIFIER_NAME].node_group == before)

    # 5.3 parameter values survive a recompile
    set_inputs(mod, {"freq": 12.0})
    edited = src.replace("sin(P.x * freq + t) * amp",
                         "sin(P.x * freq + t * 2.0) * amp")
    recompile(plane, edited)
    check("5.3 tuned freq survives an edit of the body",
          math.isclose(input_value(mod, "freq"), 12.0),
          f"freq = {input_value(mod, 'freq')}")
    added = edited.replace("amp=0.3)", "amp=0.3, lift=0.0)").replace(
        "* amp)", "* amp + lift)")
    recompile(plane, added)
    names = [i.name for i in mod.node_group.interface.items_tree
             if i.item_type == "SOCKET" and i.in_out == "INPUT"]
    check("5.3 tuned freq survives adding a parameter",
          "lift" in names and math.isclose(input_value(mod, "freq"), 12.0),
          f"inputs {names}, freq = {input_value(mod, 'freq')}")
    renamed = added.replace("freq", "f")
    recompile(plane, renamed)
    check("5.3 renamed parameter starts at its default",
          math.isclose(input_value(mod, "f"), 6.0),
          f"f = {input_value(mod, 'f')}")

    # 5.2 apply modes
    wrapper = mod.node_group
    kinds = {n.bl_idname for n in wrapper.nodes}
    check("5.2 offset wrapper: Geometry in -> Set Position -> out",
          {"NodeGroupInput", "NodeGroupOutput", "GeometryNodeSetPosition",
           "GeometryNodeGroup"} <= kinds, str(sorted(kinds)))
    bpy.context.scene.frame_set(cases.FRAME)
    recompile(plane, src, mode="absolute")
    P0 = positions(plane, evaluated=False)
    got = positions(plane)
    want = oracle_for({"source": src}, P0)
    check("5.2 absolute mode places points at the result",
          np.abs(got - want).max() < 2e-4,
          f"max err {np.abs(got - want).max():.2e}")

    # Normal mode: a number pushes each point along its own normal
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=(3.0, 0.0, 0.0))
    sphere = bpy.context.active_object
    nsrc = "def lift(P, t, amt=0.2):\n    return (P.z + 1.0) * amt\n"
    ok_compile = recompile(sphere, nsrc, mode="normal") == {"FINISHED"} and not sphere.expressnode_error
    P0 = positions(sphere, evaluated=False)
    N0 = np.array([v.normal[:] for v in sphere.data.vertices])
    got = positions(sphere)
    want = P0 + N0 * ((P0[:, 2:3] + 1.0) * 0.2)
    err = np.abs(got - want).max()
    check("5.2 normal mode pushes points along their normals",
          ok_compile and err < 2e-4, f"max err {err:.2e}, error '{sphere.expressnode_error}'")
    recompile(sphere, "def f(P, t):\n    return P * 0.1\n", mode="normal")
    check("5.2 normal mode rejects a vector result with a clear message",
          "must return a number" in sphere.expressnode_error, sphere.expressnode_error[:120])


def check_errors_in_panel():
    reset_scene()
    obj = point_object("ErrPts", 10)
    bad = {
        "loop": "def f(P):\n    for i in range(3):\n        pass\n    return P",
        "unknown name": "def f(P):\n    return sinn(P.x)",
        "string math": "def f(P):\n    return P.x + 'a'",
        "lambda": "def f(P):\n    g = lambda x: x\n    return P",
    }
    for label, src in bad.items():
        result = recompile(obj, src)
        err = obj.expressnode_error
        check(f"5.4 error '{label}' shown in panel",
              result == {"CANCELLED"} and err and "line" in err.lower(),
              err.splitlines()[0] if err else "no text")


def check_curl_noise():
    reset_scene()
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3)
    ico = bpy.context.active_object
    src = (cases._EXAMPLES / "curl_noise.py").read_text(encoding="utf-8")
    result = recompile(ico, src)
    if not check("3.4 curl-noise builds", result == {"FINISHED"},
                 ico.expressnode_error):
        return
    mod = ico.modifiers[cn_mod.MODIFIER_NAME]
    tree = expr_tree(mod)
    subs = [n for n in tree.nodes if n.bl_idname == "GeometryNodeGroup"]
    check("3.4 Expr_curl holds twelve n group nodes", len(subs) == 12,
          f"{len(subs)} group nodes, {len(tree.nodes)} nodes in total")
    if subs:
        sub = subs[0].node_tree
        ins = [i.name for i in sub.interface.items_tree
               if i.item_type == "SOCKET" and i.in_out == "INPUT"]
        outs = [i.name for i in sub.interface.items_tree
                if i.item_type == "SOCKET" and i.in_out == "OUTPUT"]
        has_noise = any(n.bl_idname == "ShaderNodeTexNoise" for n in sub.nodes)
        check("3.4 an n group holds the noise body", has_noise
              and len(outs) == 1, f"{sub.name}: in {ins}, out {outs}")
    a = positions(ico)
    bpy.context.scene.frame_set(cases.FRAME + 24)
    b = positions(ico)
    P = positions(ico, evaluated=False)
    check("3.4 the sphere swirls and animates",
          np.abs(a - P).max() > 1e-3 and np.abs(a - b).max() > 1e-4,
          f"offset up to {np.abs(a - P).max():.4f}, "
          f"frame change {np.abs(a - b).max():.4f}")
    set_inputs(mod, {"strength": 1.2})
    c = positions(ico)
    check("3.4 strength changes the result", np.abs(c - b).max() > 1e-4)


def check_objects_independent():
    reset_scene()
    a = point_object("A", 50)
    b = point_object("B", 50)
    src_a = "def ripple(P, t):\n    return vec3(0.0, 0.0, P.x)\n"
    src_b = "def ripple(P, t):\n    return vec3(0.0, 0.0, -P.x)\n"
    recompile(a, src_a)
    recompile(b, src_b)
    da = positions(a) - positions(a, evaluated=False)
    db = positions(b) - positions(b, evaluated=False)
    P = positions(a, evaluated=False)
    check("two objects with the same function name keep their own trees",
          np.allclose(da[:, 2], P[:, 0], atol=1e-5)
          and np.allclose(db[:, 2], -P[:, 0], atol=1e-5))


def check_shape_b():
    """Shape B without the node editor: build the group, drop it into a
    user's tree, wire it into Set Position, rebuild it in place."""
    from expressnode.backend import node_group as cn_ng
    reset_scene()
    obj = point_object("Host", 100)
    src = ("def offset(P, t, amp=0.3):\n"
           "    return vec3(0.0, 0.0, sin(P.x * 6.0 + t) * amp)\n")
    group = cn_ng._build_group_tree(src)
    outs = [i.name for i in group.interface.items_tree
            if i.item_type == "SOCKET" and i.in_out == "OUTPUT"]
    ins = [i.name for i in group.interface.items_tree
           if i.item_type == "SOCKET" and i.in_out == "INPUT"]
    check("4.2 expression group: amp in, Result out",
          ins == ["amp"] and outs == ["Result"], f"in {ins}, out {outs}")

    host = bpy.data.node_groups.new("Host Tree", "GeometryNodeTree")
    host.interface.new_socket("Geometry", in_out="INPUT",
                              socket_type="NodeSocketGeometry")
    host.interface.new_socket("Geometry", in_out="OUTPUT",
                              socket_type="NodeSocketGeometry")
    gi = host.nodes.new("NodeGroupInput")
    go = host.nodes.new("NodeGroupOutput")
    sp = host.nodes.new("GeometryNodeSetPosition")
    gnode = host.nodes.new("GeometryNodeGroup")
    gnode.node_tree = group
    gnode["expressnode_source"] = src
    host.links.new(gi.outputs[0], sp.inputs["Geometry"])
    host.links.new(gnode.outputs["Result"], sp.inputs["Offset"])
    host.links.new(sp.outputs[0], go.inputs[0])
    m = obj.modifiers.new("Host", "NODES")
    m.node_group = host
    P = positions(obj, evaluated=False)
    got = positions(obj) - P
    want = oracle_for({"source": src}, P)
    check("4.2 dropped group deforms the host like the oracle",
          np.abs(got - want).max() < 2e-4,
          f"max err {np.abs(got - want).max():.2e}")

    # 4.3: same compiler as Shape A
    obj2 = point_object("ShapeA", 100)
    recompile(obj2, src)
    got_a = positions(obj2) - positions(obj2, evaluated=False)
    check("4.3 Shape A gives the same result", np.abs(got_a - got).max() < 1e-6)

    # In-place update keeps the link from Result (same signature)
    src2 = src.replace("P.x * 6.0", "P.y * 3.0")
    err = cn_ng.update_group(group, src2)
    still = (gnode.node_tree == group
             and any(l.from_node == gnode for l in host.links))
    got2 = positions(obj) - P
    want2 = oracle_for({"source": src2}, P)
    check("M4 follow-up: update rebuilds the group in place, links kept",
          not err and still and np.abs(got2 - want2).max() < 2e-4,
          err or f"max err {np.abs(got2 - want2).max():.2e}")

    # A different expression that happens to share the name gets its own tree
    other = cn_ng._build_group_tree(
        "def offset(P, t):\n    return vec3(1.0, 0.0, 0.0)\n")
    check("a second, different 'offset' group doesn't overwrite the first",
          other != group and other.name.startswith("Expr_offset.")
          and gnode.node_tree == group, other.name)

    # 4.4 compile error: nothing added
    before = len(bpy.data.node_groups)
    err = cn_ng.update_group(group, "def f(P):\n    return P +")
    check("4.4 bad expression reports an error, builds nothing",
          err and len(bpy.data.node_groups) == before, err.splitlines()[0]
          if err else "no error")


def main():
    reset_scene()
    register_addon()
    guard("registration", check_registration)
    for case in cases.cases_for("gn"):
        guard(f"gn parity {case['name']}", parity_case, case)
    guard("ripple checklist", check_ripple_golden_path)
    guard("errors in panel", check_errors_in_panel)
    guard("curl noise", check_curl_noise)
    guard("independent objects", check_objects_independent)
    guard("shape b", check_shape_b)
    check("blender version", True, bpy.app.version_string)
    done()


main()

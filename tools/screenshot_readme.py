"""Make docs/readme_ripple.png: a ripple expression on a grid, its generated
Geometry Nodes tree, and the ExpressNode panel.

    blender --factory-startup --python tools/screenshot_readme.py -- <out.png>

Needs a window (it screenshots Blender's own UI); quits by itself.
"""

import os
import sys

import bpy

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import expressnode  # noqa: E402

OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(REPO, "docs", "readme_ripple.png")

EXPR = '''def ripple(P, t, freq=6.0, amp=0.25):
    r = length(vec3(P.x, P.y, 0.0))
    wave = sin(r * freq - t * 2.0)
    return vec3(0.0, 0.0, wave * amp / (1.0 + r))
'''


def setup():
    expressnode.register()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=120, y_subdivisions=120, size=4)
    grid = bpy.context.active_object
    grid.name = "Ripple"
    grid.expressnode_expression = EXPR
    bpy.ops.expressnode.recompile()
    bpy.ops.object.shade_smooth()
    bpy.context.scene.frame_set(20)

    window = bpy.context.window
    window.workspace = bpy.data.workspaces["Geometry Nodes"]
    return grid


def arrange():
    grid = bpy.data.objects["Ripple"]
    mod = next(m for m in grid.modifiers if m.type == 'NODES')
    screen = bpy.context.window.screen
    text = bpy.data.texts.new("ripple.py")
    text.write(EXPR)
    for area in screen.areas:
        if area.type == 'SPREADSHEET':
            area.type = 'TEXT_EDITOR'
            area.spaces.active.text = text
            area.spaces.active.font_size = 15
            area.spaces.active.show_line_numbers = True
            area.spaces.active.show_word_wrap = True   # never cut a line off in the picture
            area.spaces.active.top = 0
        elif area.type == 'NODE_EDITOR':
            space = area.spaces.active
            space.node_tree = mod.node_group
            region = next(r for r in area.regions if r.type == 'WINDOW')
            area.tag_redraw()
        elif area.type == 'VIEW_3D':
            area.spaces.active.shading.type = 'SOLID'
            area.spaces.active.overlay.show_overlays = True
            region = next(r for r in area.regions if r.type == 'WINDOW')
            with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
                bpy.ops.view3d.view_all()
            r3d = area.spaces.active.region_3d
            r3d.view_distance *= 0.75
        elif area.type == 'PROPERTIES':
            area.spaces.active.context = 'MODIFIER'
    return 1.0


def frame_nodes():
    """After a redraw, so the node editor knows its size: fit the whole tree."""
    for area in bpy.context.window.screen.areas:
        if area.type == 'NODE_EDITOR':
            region = next(r for r in area.regions if r.type == 'WINDOW')
            with bpy.context.temp_override(window=bpy.context.window, area=area, region=region):
                bpy.ops.node.select_all(action='DESELECT')
                bpy.ops.node.view_all()
        elif area.type == 'TEXT_EDITOR':
            area.spaces.active.top = 0
    bpy.app.timers.register(shoot, first_interval=1.5)


def shoot():
    bpy.ops.screen.screenshot(filepath=OUT)
    print("SHOT", OUT, flush=True)
    bpy.ops.wm.quit_blender()


def _go():
    arrange()
    bpy.app.timers.register(frame_nodes, first_interval=1.0)


setup()
bpy.app.timers.register(_go, first_interval=1.5)

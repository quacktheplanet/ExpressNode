# Testing ExpressNode

## Without Blender

```bash
python -m pytest tests -q
```

About 300 tests cover:
- the frontend (parsing, types, errors with line and column)
- grouping
- planning the node tree
- the OSL, GLSL and WGSL backends
- the numpy reference evaluator
- packaging
- docs that can't drift from the code: every built-in must be in `docs/expression-reference.md`

numpy is needed for the evaluator tests. Tests that need an external compiler (`oslc`, `glslangValidator`, `naga`) skip
when it's missing.

## Inside Blender

```bash
python tests/blender/run_all.py --blender <path/to/blender> [--blender <another>] \
    [--puppeteer <dir containing node_modules/puppeteer-core>] [--only gn,osl,gui,install,wgsl]
```

Blenders can also be listed in `EXPN_BLENDERS`, separated by `;`. For each Blender it runs:

| Suite | Script | What it checks |
|---|---|---|
| `gn` | `bl_gn.py` | Every case compiled to Geometry Nodes, evaluated on real geometry and compared with the reference; modifier and node-group workflows; errors in the panel |
| `osl` | `bl_osl.py` | OSL compiled with Blender's own `oslc` and rendered in Cycles, compared with the reference |
| `gui` | `bl_gui.py` | GLSL run through Blender's GPU module; the node-group workflow in a real Node Editor |
| `install` | `bl_install.py` | The extension zip installs and enables in a throwaway profile, compiles an expression, is importable as `expressnode`, and migrates files from the old add-on |

Once, it also runs `wgsl` (`tests/gpu/wgsl_parity.py`): WGSL run on WebGPU in Chrome or Edge,
compared with the reference, plus a 1M-point dispatch. It needs Node.js and puppeteer-core.

**Isolation:**
- `install` points Blender's user folders at a temporary directory and refuses to run otherwise, so
  your own profile is never touched.
- `gui` needs a window. On Windows it opens on a separate, hidden desktop, so nothing appears on
  your screen; pass `--visible` to watch it.

Release checks run on Blender 5.0.1, 5.1.2 and 5.2.2.

The original milestone-by-milestone checklist is kept in
[docs/design/TESTING-CHECKLIST.md](docs/design/TESTING-CHECKLIST.md).

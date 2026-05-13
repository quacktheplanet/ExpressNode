# 05 — Python Execution Model

## Purpose

How Python code lives inside a node, how it's compiled and executed, and
what safety/ergonomics rails surround it.

## Per-node code lifecycle

Each code-executing node holds a `code: bpy.props.StringProperty()` field.
On every evaluation, the workflow is:

1. **Get-or-compile.** Look up a cached `__code__` object keyed by
   `hash(code_string)`. If absent, `compile(code_string, '<node:NAME>',
   'exec')` and cache.
2. **Build locals.** Construct a `locals` dict containing:
   - `inputs` — a dict-like view of input socket values.
   - `outputs` — a dict that the script writes into.
   - `params` — node-level UI parameters.
   - `np` — numpy.
   - `t` — current scene time in seconds.
   - `frame` — current scene frame.
   - Optionally `scipy`, `numba` if the user enabled them in addon prefs.
3. **Build globals.** Restricted: math, numpy, and a frozen subset of
   builtins (see "Restricted execution" below).
4. **Execute.** `exec(code_object, globals, locals)`.
5. **Read outputs.** Pull values from `locals["outputs"]`.

Compilation is one-shot per code string. Execution may run thousands of
times across frames.

## Restricted execution (default)

By default, code runs in a restricted globals dict:

```python
SAFE_BUILTINS = {
    'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'float',
    'int', 'len', 'list', 'map', 'max', 'min', 'pow', 'range',
    'reversed', 'round', 'set', 'sorted', 'str', 'sum', 'tuple',
    'zip',
}

SAFE_MODULES = {
    'math': math,
    'np': np,
    'numpy': np,
}
```

What's blocked: `os`, `sys`, `subprocess`, `socket`, `open` (file IO),
`__import__`, `eval`, `exec`, and anything that touches the filesystem
or network.

A node-level checkbox **"Unrestricted execution"** removes the sandbox.
Toggling this requires a confirmation popup and a banner on the node
indicating it's unrestricted. Trust escalates explicitly.

## Why restricted by default

Not because Python sandboxing is bulletproof — it isn't — but because:

- It surfaces dangerous patterns (someone trying to `os.system(...)`
  sees a clear failure and a banner instead of silently shipping a
  vulnerable graph).
- It signals intent in `.blend` file sharing.
- It catches accidental `os.environ` reads that would make graphs
  non-portable.

For truly untrusted graphs (downloaded `.blend` files), Blender already
warns about Python execution; we don't fight that.

## Error reporting

When code raises:

1. Catch the exception in the evaluator.
2. Format a structured error:
   ```
   {
     "node_id": "abc123",
     "node_name": "Curl Noise Kernel",
     "exception_type": "ValueError",
     "message": "operands could not be broadcast together with shapes (1024,3) (1024,)",
     "traceback": "File '<node:Curl Noise Kernel>', line 7, in ..."
   }
   ```
3. Display on the node:
   - A red exclamation badge.
   - The first line of the message as a tooltip.
   - A "View traceback" button that opens a popup.
4. Stop evaluation of downstream nodes; mark them as "blocked by upstream
   error".

Errors do NOT propagate to Blender's main loop. The user keeps editing.

## Standard inputs available to every code node

| Name | Type | Source |
|---|---|---|
| `inputs` | dict-like | upstream socket values |
| `outputs` | dict (mutable) | script writes here |
| `params` | dict | node parameter properties |
| `np` | module | numpy |
| `math` | module | math stdlib |
| `t` | float | scene time in seconds |
| `frame` | int | scene frame |
| `dt` | float | frame delta |
| `seed` | int | node's seed parameter |

## Compilation cache invariants

- Keyed by `hash(code_string)`. Two nodes with identical code share a
  compiled object.
- Cleared on:
  - Addon reload.
  - Blender restart.
  - User clicking "Recompile" in the node header.
- Not cleared on:
  - Parameter changes (they don't touch the code).
  - Input changes (they don't touch the code).
  - Code edits (the new hash falls out of cache automatically).

## Performance considerations

- **Compile cost.** ~10-100 μs per compile. Negligible if code is reused.
- **Exec dispatch cost.** ~50 μs setup per call. Amortized across the
  vectorized work inside.
- **The work itself.** Numpy ops on `(N, 3)` arrays: nanoseconds per
  element for simple ops, microseconds for noise/fourier transforms.
- **Don't iterate per-point in pure Python.** That's a 100-1000× slowdown
  vs vectorized numpy.

Performance guidance is detailed in `10-performance.md`.

## Open questions

- Should we support per-node `import` of third-party packages declared in
  the addon preferences (e.g. `cv2`, `scipy.ndimage`)? **Yes**, with a UI
  for enabling specific packages.
- Should code be stored on disk per-node, or only in the `.blend`?
  **Blend-only by default**, with an export-to-file operator. Keeps
  graphs portable.
- Live reload of imported modules: opt-in via a node toggle.

## Related docs

- Node tree design: `04-node-tree-design.md`
- Geometry bridge: `06-geometry-bridge.md`
- Live update: `07-live-update.md`
- Performance: `10-performance.md`

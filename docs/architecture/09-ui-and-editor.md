# 09 — UI and Editor

## Purpose

Design the user-facing surface: how the editor appears, how code is
authored, how errors surface, how prints reach the user.

## Editor space

PyNodes registers a new editor space type alongside Blender's existing
ones (Geometry Nodes editor, Shader editor, etc.).

- Selector under the editor type dropdown: "Python Nodes".
- Same `Shift+A` add-menu pattern as other node editors.
- Same hotkeys: pan with middle-mouse, zoom with wheel, frame nodes with
  `Ctrl+J`, etc.

**Why a separate space**, not a sub-tree of the GN editor:

- The mental model differs (pull-based per-node Python vs
  per-element field).
- Sockets and link semantics differ.
- Keeping them visually separate avoids "is this a GN node or a PyNode?"
  ambiguity.
- Easier to evolve independently.

## Code editor widget

Code-executing nodes need a multi-line code editor *inside the node*.
Blender's node UI primitives don't include a code editor out of the box.
Options:

**A. Inline `prop` on the node (current best).** Use
`layout.prop(self, "code")` with `text=""`. Blender renders a small
multi-line widget. Limited: no syntax highlighting, no autocomplete,
small viewport.

**B. Dock the code to Blender's Text Editor.** Each code node has a
`text_block` pointer to a `bpy.types.Text` datablock. The user opens that
text in Blender's Text Editor for full editing with line numbers, syntax
highlighting, and the standard Python text-editor features.

**C. External editor integration.** Code lives in a file on disk; the
addon watches for changes and reloads. Maximum power, minimum embedded
UX.

**Recommendation: B as default**, with A available for small one-liners
and C as a power-user opt-in.

## Per-node UI

A code-executing node's UI:

```
+---------------------------------+
| [!] Curl Noise Kernel           |  <- header with error badge if errored
+---------------------------------+
| inputs:                          |
|   • Positions  (Vec[N,3])        |
|   • Time       (Float)           |
+---------------------------------+
| code: [Open in Text Editor]      |
|   ... or inline preview ...      |
+---------------------------------+
| Recompile  | Print Log  | ...    |
+---------------------------------+
| outputs:                         |
|   • Displacement (Vec[N,3])      |
+---------------------------------+
```

Buttons:

- **Recompile.** Forces the next evaluation to re-compile the code (in
  case the user changed an external file).
- **Print Log.** Toggles a small floating panel showing the last K
  `print()` outputs from this node.
- **Reset Cache.** Clears the node's evaluation cache.

## Error display

When evaluation fails:

- The node header gets a red exclamation badge.
- Hovering shows the exception message.
- Clicking opens a popup with the full traceback (rendered against the
  user's code, with the offending line highlighted).
- Downstream nodes show a yellow "blocked by upstream error" badge,
  unobtrusive.

The viewport does not crash. The user keeps editing.

## Print viewer

`print()` calls inside nodes are captured and tagged with the node id.
The addon exposes a small floating "Print Log" window:

```
[Curl Noise Kernel]  shape: (1024, 3), dtype: float32
[Curl Noise Kernel]  max disp: 0.4231, min: -0.4118
[Density Kernel]     iteration 5: residual=1.2e-3
```

Lines auto-clear after N seconds (configurable). The viewer is
per-tree, not per-Blender-instance, so different node trees don't share
their logs.

## Autocomplete

Inline `bpy.props.StringProperty` has no autocomplete. For users editing
in Blender's Text Editor (option B), we ship a small `pynodes.pyi` stub
file that, when included in the workspace, gives some autocomplete in
external IDEs (VS Code with Blender extension).

True in-editor autocomplete requires a custom widget. Out of scope for
phase 1.

## Theming

Match Blender's existing theme. Use the same colors for socket types
(blue for floats, purple for vectors, green for arrays). Add one new
color for `PySocketArray` (orange) to distinguish from GN's geometry
green.

## Open questions

- Could we embed Blender's Text Editor as a panel inside the node, for
  inline editing without docking? **Possibly** — investigate
  `bpy.types.SpaceTextEditor` embedding.
- Should we ship example trees in the addon's "Add → Examples" submenu?
  **Yes** — discoverability is critical for adoption.

## Related docs

- Python execution: `05-python-execution.md`
- Node tree: `04-node-tree-design.md`

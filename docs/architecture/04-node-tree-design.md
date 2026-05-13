# 04 — Node Tree Design

## Purpose

Define the structural shape of the custom node tree: tree subclass, socket
types, evaluation model.

## `PyNodeTree`

A custom `bpy.types.NodeTree` subclass.

```python
class PyNodeTree(bpy.types.NodeTree):
    bl_idname = "PyNodeTree"
    bl_label = "Python Nodes"
    bl_icon = 'SCRIPT'

    # Tracks the evaluation cache keyed by node id.
    evaluation_cache: dict[int, Any]  # not a bpy property — lives on instance
```

The tree is registered with its own Blender editor space (see
`09-ui-and-editor.md`), and its trees can be referenced by modifiers on
objects.

## Socket types

PyNodes ship a small set of typed sockets. The types matter for static
validation: connecting a `PySocketGeometry` to a `PySocketFloat` is
rejected at link time.

| Socket | Holds | Conversion notes |
|---|---|---|
| `PySocketFloat` | Python float | bool → 0/1 on input; float → bool truthy |
| `PySocketInt` | Python int | float coerces with warning |
| `PySocketVector` | `np.ndarray` shape `(3,)` or `(N,3)` | broadcast rules apply |
| `PySocketArray` | `np.ndarray` of any shape | shape recorded for downstream nodes |
| `PySocketString` | Python str | |
| `PySocketGeometry` | `GeometryHandle` (opaque) | |
| `PySocketAttribute` | `AttributeRef` (name + domain + type) | |
| `PySocketAny` | dict for arbitrary data | use sparingly; defeats type-checks |

`PySocketArray` carries shape metadata in its `default_value` UI so the
graph can show "(1024, 3) float32" inline, easing debugging.

## Node base class

```python
class PyNode(bpy.types.Node):
    bl_idname = "PyNode"  # subclasses override

    @classmethod
    def poll(cls, ntree: bpy.types.NodeTree) -> bool:
        return ntree.bl_idname == "PyNodeTree"

    def init(self, context):
        """Called when node is first added. Declare sockets here."""

    def evaluate(self, ctx: "EvalContext") -> dict[str, Any]:
        """Pure function from inputs to outputs. Subclasses override."""
        raise NotImplementedError
```

Each node has:
- `inputs` — list of input sockets.
- `outputs` — list of output sockets.
- A persistent `id` (Blender's node `bl_idname` + UUID generated at creation).
- An evaluation function returning a dict keyed by output socket name.

## Evaluation model

**Pull-based** topological evaluation:

1. The orchestrator identifies "output sinks" — nodes whose result is
   consumed externally (typically `MeshOut`, `WriteAttribute`,
   `AttributeBridge`).
2. From each sink, walk inputs backward to construct the relevant
   subgraph.
3. Topologically sort.
4. For each node in order:
   - Compute the input hash from upstream-cached results + node parameters.
   - If `cache[(node.id, input_hash)]` exists, reuse it.
   - Otherwise call `node.evaluate(ctx)`, store in cache.

This is the same model as Geometry Nodes', minus the per-point parallelism.

```python
def evaluate_tree(tree: PyNodeTree, sinks: list[PyNode]) -> dict[PyNode, dict]:
    order = topo_sort(reachable_from(sinks))
    results = {}
    for node in order:
        input_values = {
            sock.name: results[sock.linked_from.node][sock.linked_from.name]
            for sock in node.inputs if sock.is_linked
        }
        key = (node.id, hash_inputs(input_values, node.parameters))
        if key in tree._cache:
            results[node] = tree._cache[key]
        else:
            ctx = EvalContext(inputs=input_values,
                              params=node.parameters)
            results[node] = node.evaluate(ctx)
            tree._cache[key] = results[node]
    return results
```

## Type checking

When a user attempts to link two sockets, Blender calls our `update()`
handler. We:

1. Verify the source output type and the target input type are compatible
   (or compatible after a documented conversion).
2. If incompatible, remove the link and add a diagnostic to the target
   node's error display.

Allowed conversions:
- Float ↔ Int (with warning on float→int).
- Float → Vector (broadcast `(f, f, f)`).
- `Any` accepts anything but propagates a warning downstream.

## Node ID stability

Blender's node UUIDs are stable across saves *but not across deletes*.
For caching, we additionally store a stable `node.user_id` set on
creation. Cache invalidation uses `user_id`, so renaming or temporarily
disconnecting doesn't bust the cache.

## Open questions

- Should sockets carry units (e.g. radians vs degrees)? Probably no — the
  user manages units.
- Group nodes (subgraphs as nodes)? Yes, eventually — mirror Blender's
  group node semantics. Phase 2.
- Frame nodes for organization? Free from Blender's built-in `NodeFrame`.

## Related docs

- Python execution: `05-python-execution.md`
- Geometry bridge: `06-geometry-bridge.md`
- Live update: `07-live-update.md`
- Node reference: `../api/node-reference.md`

# 07 — Live Update

## Purpose

When the user changes a parameter, edits code, or scrubs the timeline, the
graph must re-evaluate the affected nodes (and only those) and push the
result to Blender's scene without stalling the UI.

## Update sources

Five sources of "something changed":

| Source | Trigger |
|---|---|
| Parameter change | User edits a node property |
| Code edit | User edits a code field and clicks Recompile (or auto-commit on focus loss) |
| Input change | Upstream node's output changed |
| Frame change | Scene timeline scrubbed or playing |
| External change | A linked Blender datablock was modified |

Each source maps to one or more invalidations.

## Depsgraph hooks

The addon installs handlers:

```python
import bpy
from bpy.app.handlers import persistent

@persistent
def on_depsgraph_update(scene, depsgraph):
    for update in depsgraph.updates:
        if isinstance(update.id.original, bpy.types.Object):
            invalidate_node_caches_using(update.id.original)

bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
```

The handler is *fast*: it only invalidates caches, never re-evaluates.
Re-evaluation happens lazily on the next pull.

## Frame change

```python
@persistent
def on_frame_change(scene, depsgraph):
    invalidate_time_dependent_nodes()
    schedule_reevaluation()
```

Time-dependent nodes are flagged at creation (e.g. `NumpyKernel` with `t`
or `frame` referenced in its code triggers the flag).

## Dependency tracking

Caches are keyed by `(node.user_id, input_hash)`:

- `input_hash` is computed from upstream output values and the node's
  own parameter values.
- If only one parameter changed, only nodes downstream of that parameter
  are recomputed.
- Time-dependent nodes always re-hash on frame change (their hash
  includes `frame`).

```python
def input_hash(node, upstream_values):
    parts = [hash(tuple(node.parameters.items()))]
    for sock in node.inputs:
        val = upstream_values.get(sock.name)
        parts.append(_stable_hash(val))
    return hash(tuple(parts))
```

`_stable_hash` handles numpy arrays via shape + a sample digest (full
hashing is too expensive for large arrays; we accept a small false-positive
rate of "thought it changed but didn't" in exchange for fast hashing).

## Throttling

For sustained changes (scrubbing the timeline, dragging a slider):

- Coalesce events: drop redundant invalidations within a 16ms window.
- Cap re-evaluation rate to ~30 Hz in the viewport.
- For heavy graphs, the user sees a small "Computing..." indicator and a
  stale viewport until ready.

## Async evaluation (later)

Pure Python evaluation blocks the main thread. For large graphs, this
shows as UI hangs. Mitigations:

- Phase 1: accept the hangs; document them. Most graphs evaluate < 100ms.
- Phase 2: move evaluation to a worker thread, post results back via a
  modal operator. The GIL is still in play, but numpy ops release it
  internally for many operations, so workers help.
- Phase 3: process-based workers via `multiprocessing` for truly heavy
  graphs. Adds significant complexity (serialization, IPC).

## Cache invalidation rules

| Event | What's invalidated |
|---|---|
| Parameter change on node N | N's cache + everything downstream of N |
| Code change on node N | Same as parameter change |
| Link change on node N | Same as parameter change |
| Frame change | All time-dependent nodes + their downstream |
| Depsgraph update of object O | All nodes referencing O |
| Addon reload | Everything |

Invalidation does not recompute — it only removes cache entries. The next
pull re-evaluates.

## Cache size

The cache lives in Python memory. For large geometries, this grows
quickly:

- Bound by total entries (not bytes), default 64 entries per node.
- LRU eviction within each node.
- Optional global byte budget in addon preferences (off by default;
  surprisingly hard to measure numpy ownership correctly).

## Open questions

- How to surface "graph evaluation in progress" without flicker? **A
  subtle header badge** rather than a popup.
- Should the cache persist across Blender restarts (on-disk)? Probably no
  — startup cost outweighs hit benefit for fast graphs, and slow graphs
  benefit more from a fresh start.
- Hash strategy for huge numpy arrays — use `numpy.lib.format` magic, or
  `xxhash`? **xxhash on shape + a strided sample**, full hash only when
  shape/sum is suspicious.

## Related docs

- Python execution: `05-python-execution.md`
- GN interop: `08-gn-interop.md`
- Performance: `10-performance.md`

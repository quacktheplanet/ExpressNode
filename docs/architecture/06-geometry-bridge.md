# 06 — Geometry Bridge

## Purpose

Define how PyNodes exchange geometry data (positions, normals, faces,
attributes) with Blender datablocks. The bridge is performance-critical:
millions of points may move per frame.

## Representations

PyNodes works in three representations:

1. **Numpy arrays.** The primary in-graph form.
2. **`bmesh.types.BMesh`.** For topology edits.
3. **`bpy.types.Mesh` / `PointCloud` / `Curves`.** Blender datablocks at
   the bridge boundary.

## Read: Blender datablock → numpy

The fast path uses `foreach_get`, not iteration:

```python
mesh = obj.data
n = len(mesh.vertices)
positions = np.empty(n * 3, dtype=np.float32)
mesh.vertices.foreach_get('co', positions)
positions = positions.reshape(n, 3)

normals = np.empty(n * 3, dtype=np.float32)
mesh.vertices.foreach_get('normal', normals)
normals = normals.reshape(n, 3)
```

`foreach_get` is ~100× faster than `[v.co for v in mesh.vertices]`.

Named attributes are read similarly:

```python
attr = mesh.attributes["my_attribute"]
data = np.empty(n, dtype=np.float32)
attr.data.foreach_get('value', data)
```

For vector attributes, allocate `n * 3` and reshape.

## Write: numpy → Blender datablock

`foreach_set` is the inverse:

```python
mesh.vertices.foreach_set('co', positions.ravel())
mesh.update()
```

For named attributes:

```python
attr = mesh.attributes.get(name) or mesh.attributes.new(
    name, type='FLOAT', domain='POINT'
)
attr.data.foreach_set('value', data.ravel())
```

After writes, call `mesh.update()` once at the end of the bridge node, not
between writes.

## Topology edits

For changes that modify edges/faces (subdivide, dissolve, bridge edges,
extrude), use `bmesh`:

```python
import bmesh
bm = bmesh.new()
bm.from_mesh(mesh)
# ...edit bm...
bm.to_mesh(mesh)
bm.free()
```

`bmesh` is slower per-element than numpy but it's the only way to do
topology in-Python at acceptable speed. The bridge nodes that do topology
work hide the bmesh dance from the user.

## `GeometryHandle`

In-graph geometry is wrapped in an opaque handle:

```python
@dataclass
class GeometryHandle:
    kind: Literal["mesh", "points", "curves"]
    positions: np.ndarray            # (N, 3) float32
    normals: np.ndarray | None       # (N, 3) float32 — for mesh only
    faces: np.ndarray | None         # (M, K) int32 — variable-K supported
    attributes: dict[str, np.ndarray]
    metadata: dict
```

Nodes that consume geometry expect a `GeometryHandle`; nodes that produce
it construct one. The bridge nodes (`MeshIn` / `MeshOut` /
`PointCloudOut`) convert to/from Blender datablocks.

## Curves

Blender's `Curves` datablock (hair-curves API) is the target for curve
output. Access via `foreach_get`/`foreach_set` on `points.position`:

```python
curves = obj.data
# Note: total point count is across all curves
n = len(curves.points)
positions = np.empty(n * 3, dtype=np.float32)
curves.points.foreach_get('position', positions)
```

Curve topology (which points belong to which curve) is in
`curves.curve_offsets`.

## Attribute domains

Blender attributes live on a domain:

| Domain | What |
|---|---|
| `POINT` | Per-vertex |
| `EDGE` | Per-edge |
| `FACE` | Per-face |
| `CORNER` | Per-loop (face-corner) |
| `CURVE` | Per-curve (for Curves datablock) |
| `INSTANCE` | Per-instance (for instances) |

A `PySocketAttribute` carries `(name, type, domain)`. The bridge ensures
the destination datablock has matching domain support.

## Memory and zero-copy aspirations

`foreach_get`/`foreach_set` allocate fresh numpy buffers each call.
There's no zero-copy story today; Blender doesn't expose its internal
storage as a numpy view.

For the largest geometries, this is a real cost: a 10M-vertex mesh
allocates ~120 MB of float32 per read. Mitigations:
- Cache reads aggressively (the evaluation cache helps).
- Read once into a `GeometryHandle`, pass that through the graph by
  reference.
- Encourage in-place numpy operations (`positions[:, 2] += offset`
  instead of `positions = positions + offset_vec`).

## Open questions

- Could we use Blender's `numpy` C-API integration to get zero-copy views
  on attribute storage? **Investigate** — would be a major performance win.
- Curve topology mutation (add/remove curves at runtime) is awkward;
  is it worth a high-level `CurvesEdit` node? Yes, in phase 2.

## Related docs

- Node tree: `04-node-tree-design.md`
- GN interop: `08-gn-interop.md`
- Performance: `10-performance.md`

# Node Reference

Pseudocode reference for the proposed PyNodes node library. No
implementation exists yet; these signatures define the contract the
implementation must satisfy.

## Base classes

```python
class PyNode(bpy.types.Node):
    bl_idname = "PyNode"

    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == "PyNodeTree"

    def init(self, context):
        """Declare sockets and default UI."""

    def evaluate(self, ctx: EvalContext) -> dict[str, Any]:
        raise NotImplementedError

    def draw_buttons(self, context, layout):
        """Per-node UI in the node body."""

    def draw_buttons_ext(self, context, layout):
        """Per-node UI in the sidebar (N-panel)."""
```

## Code-executing nodes

### `PyExprNode`
**Purpose:** Single Python expression evaluated against inputs.

```python
class PyExprNode(PyNode):
    bl_label = "Python Expression"

    code: bpy.props.StringProperty(
        name="Expression",
        default="inputs['x'] * 2",
        description="A single Python expression evaluated against inputs."
    )

    # Inputs and outputs are defined by the user via "Add Socket" buttons.

    def evaluate(self, ctx):
        code_obj = compile(self.code, f"<expr:{self.name}>", "eval")
        locals_ = {**ctx.inputs, "np": np, "math": math,
                   "t": ctx.time, "frame": ctx.frame}
        value = eval(code_obj, RESTRICTED_GLOBALS, locals_)
        return {"out": value}
```

### `NumpyKernelNode`
**Purpose:** Multi-line numpy kernel with named inputs and outputs.

```python
class NumpyKernelNode(PyNode):
    bl_label = "Numpy Kernel"

    code: bpy.props.StringProperty(
        name="Code",
        default="outputs['out'] = inputs['x']",
        description="Multi-line numpy kernel. Read inputs from `inputs`, "
                    "write to `outputs`."
    )

    def evaluate(self, ctx):
        code_obj = compile(self.code, f"<kernel:{self.name}>", "exec")
        locals_ = {
            "inputs": dict(ctx.inputs),
            "outputs": {},
            "params": dict(ctx.params),
            "np": np, "math": math,
            "t": ctx.time, "frame": ctx.frame, "dt": ctx.dt,
            "seed": self.seed,
        }
        exec(code_obj, RESTRICTED_GLOBALS, locals_)
        return locals_["outputs"]
```

### `SDFFunctionNode`
**Purpose:** Python-defined SDF: takes positions, returns distances.

```python
class SDFFunctionNode(PyNode):
    bl_label = "SDF Function"

    code: bpy.props.StringProperty(
        default=(
            "# p: (N, 3) positions; return (N,) distances\n"
            "return np.linalg.norm(p, axis=-1) - 1.0"
        ),
    )

    def evaluate(self, ctx):
        # Wrap code in a function definition for clean return semantics.
        fn_src = f"def _sdf(p):\n" + "\n".join(
            "    " + line for line in self.code.splitlines()
        )
        scope = {"np": np, "math": math}
        exec(fn_src, RESTRICTED_GLOBALS, scope)
        return {"sdf": SDF(scope["_sdf"])}
```

## Geometry I/O nodes

### `MeshInNode`
**Purpose:** Read an object's mesh into a `GeometryHandle`.

```python
class MeshInNode(PyNode):
    bl_label = "Mesh In"

    object: bpy.props.PointerProperty(type=bpy.types.Object)
    use_evaluated: bpy.props.BoolProperty(default=False)

    def evaluate(self, ctx):
        obj = self.object
        if obj is None:
            return {"geometry": None}
        mesh = (obj.evaluated_get(ctx.depsgraph).data
                if self.use_evaluated else obj.data)
        return {"geometry": read_mesh_to_handle(mesh)}
```

### `MeshOutNode`
**Purpose:** Write a `GeometryHandle` back into an object's mesh.

```python
class MeshOutNode(PyNode):
    bl_label = "Mesh Out"

    target_object: bpy.props.PointerProperty(type=bpy.types.Object)

    def evaluate(self, ctx):
        handle = ctx.inputs["geometry"]
        if self.target_object and handle:
            write_handle_to_mesh(self.target_object.data, handle)
        return {}
```

### `PointCloudOutNode`
Same shape as `MeshOutNode`, but writes to a `PointCloud` datablock.

### `CurvesOutNode`
Same shape, writes to a `Curves` datablock.

## Attribute nodes

### `ReadAttributeNode`
```python
class ReadAttributeNode(PyNode):
    bl_label = "Read Attribute"

    object: bpy.props.PointerProperty(type=bpy.types.Object)
    attribute_name: bpy.props.StringProperty(default="my_attr")

    def evaluate(self, ctx):
        data = read_attribute(self.object, self.attribute_name)
        return {"data": data}
```

### `WriteAttributeNode`
```python
class WriteAttributeNode(PyNode):
    bl_label = "Write Attribute"

    object: bpy.props.PointerProperty(type=bpy.types.Object)
    attribute_name: bpy.props.StringProperty(default="my_attr")
    domain: bpy.props.EnumProperty(items=[...])
    dtype: bpy.props.EnumProperty(items=[...])

    def evaluate(self, ctx):
        data = ctx.inputs["data"]
        write_attribute(self.object, self.attribute_name,
                        data, self.domain, self.dtype)
        return {"object": self.object}
```

### `AttributeBridgeNode`
Combines write + passthrough for chaining.

## Helper nodes

### `TimeNode`
```python
class TimeNode(PyNode):
    bl_label = "Time"

    def evaluate(self, ctx):
        return {
            "seconds": ctx.time,
            "frame": ctx.frame,
            "dt": ctx.dt,
        }
```

### `ConstantNode`
```python
class ConstantNode(PyNode):
    bl_label = "Constant"

    type: bpy.props.EnumProperty(items=["FLOAT", "INT", "VECTOR", "STRING"])
    float_value: bpy.props.FloatProperty()
    int_value: bpy.props.IntProperty()
    vector_value: bpy.props.FloatVectorProperty(size=3)
    string_value: bpy.props.StringProperty()

    def evaluate(self, ctx):
        return {"value": getattr(self, f"{self.type.lower()}_value")}
```

### `RangeNode`
```python
class RangeNode(PyNode):
    bl_label = "Range"

    def evaluate(self, ctx):
        # numpy.arange-style array of indices
        return {"out": np.arange(ctx.inputs["count"])}
```

## Geometry derivation nodes

### `PositionsNode`
Extracts the positions array `(N, 3)` from a `GeometryHandle`.

### `NormalsNode`
Same, for normals.

### `SetPositionsNode`
Replaces a `GeometryHandle`'s positions with a new array.

## Field nodes (shorthands for common kernels)

The library ships a handful of pre-built kernels as nodes — implementations
are `NumpyKernelNode` subclasses with the code baked in:

- `CurlNoiseNode` — 3D curl noise field, vectorized.
- `PerlinNoiseNode` — scalar Perlin.
- `VoronoiNode` — voronoi distance + cell index.
- `GradientNode` — directional gradient.
- `RadialNode` — radial distance / angle decomposition.

Each takes a positions input and outputs the corresponding field array.

## SDF nodes

- `SDFSphereNode`, `SDFBoxNode`, `SDFTorusNode` — primitive SDFs.
- `SDFUnionNode`, `SDFSubtractNode`, `SDFIntersectNode` — boolean ops.
- `SDFSmoothUnionNode` — with `k` parameter.
- `SDFToMeshNode` — marching-cubes via skimage.
- `SDFSampleNode` — evaluate an SDF at given positions.

## Output / control nodes

- `IfNode` — conditional routing based on a boolean expression.
- `SwitchNode` — pick one of N inputs by index.
- `PrintNode` — log inputs to the print viewer (passthrough).
- `AssertNode` — assert a condition; error if false.

## Related docs

- Node tree design: `../architecture/04-node-tree-design.md`
- Python execution: `../architecture/05-python-execution.md`
- Examples: `../examples/displace-with-python.md`

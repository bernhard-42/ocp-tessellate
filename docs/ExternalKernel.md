# Writing a kernel plugin for ocp_tessellate

ocp_tessellate meshes OCCT shapes. Objects of another kernel (SMLib through smlibpy, or any kernel that can triangulate its own bodies) are shown through `OcpExternalObject`: the plugin brings the functions that mesh its objects, and the pipeline treats them like OCCT objects. This page lists the five functions a plugin writes, in the order to write them. The smlibpy plugin (`viewer.py` of the smlib prototype) is the reference; `tests/test_external_objects.py` checks the pipeline's side with a synthetic kernel.

What the pipeline does for the plugin: names and unique names, colors and the default color of a kind, the viewer's config and every `show` keyword, the resolution of `deviation`, `angular_tolerance` and `helper_scale` from keywords and `set_defaults`, the tree of groups and parts, the wire format, sending, and mixing with build123d, CadQuery and OCCT objects in one scene. What it does not: tessellate (steps 1 to 3 do), and measure. An external object has no entry in the model of the measurement backend, which holds OCCT shapes; the properties and distance tools show nothing for it, see "Measuring" at the end. ocp_tessellate still needs OCP or nanocct installed, since `_kernel` requires one at import.

A plugin exports two functions, `<kernel>_show` and `<kernel>_show_all` (step 5). Everything else is its own; the building blocks of steps 4 and 5 come from `ocp_tessellate.plugin`.

## 1. The tessellation contract

Four functions. Steps 1 to 3 produce the data `tessellate_group` consumes; step 4 wires them to the objects.

### Step 1: `tessellate(body, quality, angular_tolerance, compute_edges) -> Tessellation`

The triangulation of a solid, shell, sheet or face, in the layout the viewer wants. The pipeline calls it (through step 3) with the values the host resolved:

| argument | meaning |
|---|---|
| `quality` | the chord deviation to mesh to, in model units: `compute_quality(bounding_box, deviation)`, the mean size of the box over 100 times the viewer's `deviation` (default 0.1) |
| `angular_tolerance` | the largest angle between neighbouring facet normals, in radians (default 0.2) |
| `compute_edges` | whether the edges are wanted; the pipeline asks for them today |

The `Tessellation` it returns is a dict of flat numpy arrays (`ocp_tessellate.types.Tessellation`), laid out for three.js:

| key | dtype | content |
|---|---|---|
| `vertices` | float32, 3 V | the points, face by face: every face owns a contiguous block of vertices, and a point on the border between two faces appears once per face |
| `normals` | float32, 3 V | one normal per vertex, the surface normal of the vertex's face at that point; a point where the normals of one face differ (the apex of a cone) is split into one vertex per normal |
| `triangles` | int32, 3 T | vertex indices, counter-clockwise seen from outside, the triangles of a face contiguous |
| `triangles_per_face` | int32, F | triangles of each face, in face order |
| `face_types` | int32, F | `GeomAbs_SurfaceType` values, by name in `ocp_tessellate.plugin.SURFACE_TYPES`: `Plane` 0, `Cylinder` 1, `Cone` 2, `Sphere` 3, `Torus` 4, `BezierSurface` 5, `BSplineSurface` 6, `SurfaceOfRevolution` 7, `SurfaceOfExtrusion` 8, `OffsetSurface` 9, `OtherSurface` 10 |
| `edges` | float32, 6 S | the segments of the edges as point pairs, edge by edge |
| `segments_per_edge` | int32, E | segments of each edge, in edge order; 0 for an edge without segments |
| `edge_types` | int32, E | `GeomAbs_CurveType` values, by name in `ocp_tessellate.plugin.CURVE_TYPES`: `Line` 0, `Circle` 1, `Ellipse` 2, `Hyperbola` 3, `Parabola` 4, `BezierCurve` 5, `BSplineCurve` 6, `OffsetCurve` 7, `OtherCurve` 8 |
| `obj_vertices` | float32, 3 O | the body's vertices |

Faces, edges and vertices are numbered in the order of these arrays: the viewer names them `faces_i`, `edges_i`, `vertices_i` for picking, so a face without triangles still takes an entry (0 in `triangles_per_face`, its type in `face_types`), and an edge without segments one in `segments_per_edge`.

Edges should be sampled so that every segment's chord lies within a tenth of `quality` of the curve, which is what the OCCT path does (`deflection = quality / 10`). A straight edge is one segment.

Welded meshes, where faces share points and normals belong to triangle corners, have to be unwelded: sort the triangles by face, and within a face give one vertex to each distinct (point, normal) pair.

#### Example: the unit box

`Box(1, 1, 1)` centred at the origin, as smlibpy tessellates it (identical to the OCCT path as a set of vertex and normal pairs). Six faces with four vertices each, so 24 vertices for 8 corner points: every corner appears once per face that meets there, with that face's normal.

```python
{
    # 24 vertices, a block of 4 per face; face f owns vertices 4f .. 4f+3
    "vertices": np.array([
        [-0.5, -0.5, -0.5], [-0.5, 0.5, -0.5], [0.5, 0.5, -0.5], [0.5, -0.5, -0.5],   # face 0, normal [0, 0, -1]
        [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5], [-0.5, 0.5, 0.5], [0.5, 0.5, 0.5],   # face 1, normal [0, 0, 1]
        [-0.5, -0.5, -0.5], [-0.5, 0.5, -0.5], [-0.5, -0.5, 0.5], [-0.5, 0.5, 0.5],   # face 2, normal [-1, 0, 0]
        [0.5, 0.5, -0.5], [0.5, -0.5, -0.5], [0.5, -0.5, 0.5], [0.5, 0.5, 0.5],   # face 3, normal [1, 0, 0]
        [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5], [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5],   # face 4, normal [0, -1, 0]
        [-0.5, 0.5, -0.5], [0.5, 0.5, -0.5], [-0.5, 0.5, 0.5], [0.5, 0.5, 0.5],   # face 5, normal [0, 1, 0]
    ], dtype=np.float32).ravel(),
    # one normal per vertex: the face normal, 4 times per face
    "normals": np.array([
        *[[0, 0, -1]] * 4,   # face 0
        *[[0, 0, 1]] * 4,   # face 1
        *[[-1, 0, 0]] * 4,   # face 2
        *[[1, 0, 0]] * 4,   # face 3
        *[[0, -1, 0]] * 4,   # face 4
        *[[0, 1, 0]] * 4,   # face 5
    ], dtype=np.float32).ravel(),
    # 12 triangles, 2 per face, indices into the face's own block
    "triangles": np.array([
        [0, 2, 3], [2, 0, 1],   # face 0
        [4, 7, 6], [7, 4, 5],   # face 1
        [8, 11, 9], [11, 8, 10],   # face 2
        [13, 15, 14], [15, 13, 12],   # face 3
        [16, 19, 18], [19, 16, 17],   # face 4
        [20, 23, 21], [23, 20, 22],   # face 5
    ], dtype=np.int32).ravel(),
    "triangles_per_face": np.array([2, 2, 2, 2, 2, 2], dtype=np.int32),
    "face_types": np.array([0, 0, 0, 0, 0, 0], dtype=np.int32),   # all planes
    # 12 edges, one segment each: the two end points of every edge
    "edges": np.array([
        [0.5, -0.5, 0.5], [0.5, 0.5, 0.5], [-0.5, 0.5, 0.5], [0.5, 0.5, 0.5],
        [-0.5, -0.5, -0.5], [-0.5, 0.5, -0.5], [-0.5, -0.5, 0.5], [-0.5, 0.5, 0.5],
        [0.5, -0.5, -0.5], [0.5, 0.5, -0.5], [0.5, 0.5, -0.5], [0.5, 0.5, 0.5],
        [-0.5, -0.5, -0.5], [-0.5, -0.5, 0.5], [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5],
        [0.5, -0.5, -0.5], [0.5, -0.5, 0.5], [-0.5, -0.5, 0.5], [0.5, -0.5, 0.5],
        [-0.5, 0.5, -0.5], [-0.5, 0.5, 0.5], [-0.5, 0.5, -0.5], [0.5, 0.5, -0.5],
    ], dtype=np.float32).ravel(),
    "segments_per_edge": np.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], dtype=np.int32),
    "edge_types": np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.int32),   # all lines
    # the 8 corner points
    "obj_vertices": np.array([
        [0.5, 0.5, 0.5], [-0.5, -0.5, 0.5], [-0.5, -0.5, -0.5], [0.5, -0.5, -0.5],
        [0.5, -0.5, 0.5], [-0.5, 0.5, 0.5], [-0.5, 0.5, -0.5], [0.5, 0.5, -0.5],
    ], dtype=np.float32).ravel(),
}
```

### Step 2: `discretize_edges(edges, deviation, edge_accuracy) -> DiscretizedEdges`

The segments of edges shown on their own (a list of edges, a wire). `DiscretizedEdges` is a dict with `edges`, `segments_per_edge`, `edge_types` and `obj_vertices` as in step 1, `obj_vertices` the end points. The chord deviation is `edge_accuracy` when the viewer has one (None by default), else a tenth of `compute_quality(box of the edges, deviation)`, the OCCT path's rule. A straight edge is one segment.

#### Example: a rectangle with an arc

A wire of three lines and an arc, the 2 x 1 rectangle whose top side is the arc through (1, 1.5, 0), radius 1.25:

```python
wire = Wire([Line((0, 0, 0), (2, 0, 0)), Line((2, 0, 0), (2, 1, 0)),
             ThreePointArc((2, 1, 0), (1, 1.5, 0), (0, 1, 0)), Line((0, 1, 0), (0, 0, 0))])
discretize_edges(wire.edges(), deviation=0.1)
```

The box is 2 x 1.5, so `quality` is about 0.0012 and the chord deviation a tenth of that. Each line is one segment; the arc gets 76 segments. Four edges, so `segments_per_edge` and `edge_types` have four entries; `obj_vertices` holds the four corners once each.

```python
{
    # 79 segments, point pairs (start, end), edge by edge
    "edges": np.array([
        [0, 0, 0], [2, 0, 0],   # edge 0, a line: one segment
        [2, 0, 0], [2, 1, 0],   # edge 1, a line: one segment
        [2, 1, 0], [1.9814, 1.0242, 0],   # edge 2, the arc: 76 segments
        [1.9814, 1.0242, 0], [1.9622, 1.0479, 0],
        ...,
        [0.0186, 1.0242, 0], [0, 1, 0],
        [0, 1, 0], [0, 0, 0],   # edge 3, a line: one segment
    ], dtype=np.float32).ravel(),
    "segments_per_edge": np.array([1, 1, 76, 1], dtype=np.int32),
    "edge_types": np.array([0, 0, 1, 0], dtype=np.int32),   # line, line, circle, line
    "obj_vertices": np.array([[0, 0, 0], [2, 0, 0], [2, 1, 0], [0, 1, 0]], dtype=np.float32).ravel(),
}
```

Vertices need no function: they are points, step 4 passes their coordinates.

### Step 3: `bounding_box(body) -> BoundingBox`

The box of a solid, shell or face as an `ocp_tessellate.ocp_utils.BoundingBox`, built from the kernel's extremes: `BoundingBox({"xmin": ..., "xmax": ..., "ymin": ..., "ymax": ..., "zmin": ..., "zmax": ...})`. It gives `quality` (`compute_quality`), the camera and relative `helper_scale` values. A flat body has a zero extent, which is fine.

### Step 4: `convert(obj, name, color, alpha) -> OcpExternalObject | OcpGroup`

The orchestrator: one object of the kernel into what the pipeline takes, by dispatching on its type onto four functions ocp_tessellate provides. A list or dict becomes an `OcpGroup` of converted children, named `Face(i)`, `Edge(i)`, `Vertex(i)` or by the dict's keys.

```python
from ocp_tessellate import OcpGroup
from ocp_tessellate.plugin import OcpExternalObject, external_tessellate, external_edges, external_coord_system, external_coord_axis
```

| the kernel's object | call |
|---|---|
| solid | `external_tessellate("solid", name, body, tessellate, bounding_box, cache_id=None, color=None, alpha=None)` |
| shell, sheet | `external_tessellate("shell", ...)` |
| sketch, face | `external_tessellate("face", ...)`, drawn on both sides (`renderback`) |
| edge, wire | `external_edges(name, edges, discretize_edges, color, alpha)` |
| vertex, point | `OcpExternalObject("vertex", name, points=[(x, y, z)], color=color)` |
| location, plane (optional) | `external_coord_system(name, origin, x_dir, z_dir)` |
| axis (optional) | `external_coord_axis(name, origin, direction, color)` |

- `external_tessellate` takes the kernel's `tessellate` of step 1 and calls it through ocp_tessellate's tessellation cache (see step 4a), with the body bound and `quality`, `angular_tolerance` and `compute_edges` as the host resolved them. The plugin supplies two values:
  - `bounding_box`, the box of step 3.
  - `cache_id`, optional, the opt-in to caching (step 4a): a string that identifies the geometry, not the Python object, equal for a body built twice, different for a moved copy. A plugin that wants caching defines a function `_cache_id(body) -> str` (any name will do) and passes its result; smlibpy's hashes the body's binary native file. `None`, the default, means the body is meshed at every show.
- `external_edges` takes the kernel's `discretize_edges` of step 2 and whatever `edges` it accepts (a list of edges, a wire's edges), calls it with `deviation` and `edge_accuracy` as the host resolved them, and boxes the segments.
- `color` takes what `Color()` takes: a web color name, `#rrggbb`, a tuple, a `Color`; `alpha` is applied to it. Without a color, `external_tessellate` uses the body's own `color` attribute if it has one; otherwise the object stays uncolored and the pipeline gives it the host's default of its kind: `default_color` for a solid, `default_facecolor` for a face or shell, `default_thickedgecolor` for an edge, `default_vertexcolor` for a vertex.
- `external_coord_system` and `external_coord_axis` draw a location, plane or axis as edge leaves of one-segment edges, sized by the `helper_scale` the host resolves: the x, y and z axes in red, green and blue, or the shaft and the ten segments of a pyramid head, black by default. They draw the same points as `CoordSystem` and `CoordAxis` do for OCCT objects (the pyramid's directions follow OCCT's `gp_Ax2` rule), which `tests/test_external_objects.py` checks. Alternatively such an object is converted to a `TopLoc_Location`, `gp_Pln` or `gp_Ax1` of `kernel()` and goes the OCCT way.

#### Step 4a: caching (optional): `_cache_id(body) -> str`

With a `cache_id`, `external_tessellate` puts the kernel's `tessellate` into the cache of the OCCT tessellator (`ocp_tessellate.tessellator.cache`, keyed as `make_key` keys OCCT shapes: `cache_id`, `deviation`, `angular_tolerance`, `compute_edges`). A body built twice with the same `cache_id` is meshed once; the progress line shows `+` for a mesh and `c` for a hit. Without a `cache_id` nothing is cached. The plugin's whole part is the function that computes it, from the geometry and nothing else:

```python
def _cache_id(body: SmlibBody) -> str:
    return hashlib.sha256(to_smb(body, ascii=False)).hexdigest()  # smlib's binary native file: 3 ms for 180 faces
```

## 2. The show contract

### Step 5: `<kernel>_show(*objects, names, colors, alphas, **kwargs)` and `<kernel>_show_all(...)`

The two exported functions. `<kernel>_show` builds the scene with ocp_tessellate's `external_scene(objects, convert, names, colors, alphas)`, which converts every object with the plugin's `convert` of step 4 (an `OcpExternalObject` or an `OcpGroup` each, a `TypeError` for anything else) and aligns `names`, `colors` and `alphas` to the objects as `show` does, and hands the scene with the three lists and every keyword it was given to the host's `show`: `reset_camera`, `collapse`, `helper_scale`, `transparent`, ... all apply, and so do `set_defaults`. The host's `show` is `from ocp_viewer_core.viewer import show`, imported at the top of the plugin, which picks ocp_vscode, jupyter_cadquery, build123d_studio or ocp_viewer from the environment. To show the kernel's objects beside build123d, CadQuery or OCCT objects, hand `convert(obj, name)` to the host's `show` together with them: the pipeline mixes them.

`<kernel>_show_all` walks the caller's scope for the kernel's objects (bodies, faces, edges, wires, vertices, vectors, locations, planes, axes, and lists or dicts of them) and shows them under their variable names, as the hosts' `show_all` does.

### Measuring (optional): `to_occt(obj, binding=None)`

External objects cannot be measured. A kernel that can write its bodies in a form OCCT reads may offer a converter, so that `show(to_occt(obj))` draws and measures the object as an OCCT shape: bodies through an exchange format (the kernel's `.brep` writer and `BRepTools.Read_s`, or STEP), edges as exact lines or `Geom_BSplineCurve`s from the kernel's NURBS data, wires with `BRepBuilderAPI_MakeWire`, points with `BRepBuilderAPI_MakeVertex`, locations as `TopLoc_Location` from the 4x4 matrix (`gp_Trsf.SetValues`), planes as `gp_Pln`, axes as `gp_Ax1`; lists and dicts element-wise. `binding` is `"OCP"` or `"nanocct"`, by default `ocp_tessellate._kernel.kernel()`; the collection classes differ between the bindings and OCP versions (`NCollection_Array1__gp_Pnt`, `TColgp_Array1OfPnt`, `OCP.collections.Array1_gp_Pnt`), and `BRepTools.Read_s` takes a text stream in nanocct and a bytes stream in OCP. It is a separate way of showing: OCCT numbers the sub-shapes differently from step 1, names and colors are not in the exchange formats, and it may fail for geometry the writer cannot express (smlibpy's `.brep` writer refuses offset surfaces of free-form faces); raise a `ValueError` that names `<kernel>_show` as the way to at least see the object.

## 3. A complete toy plugin

A kernel whose only body is a triangle, every step in place, runnable as it stands:

```python
import numpy as np
from ocp_tessellate import OcpGroup
from ocp_tessellate.plugin import CURVE_TYPES, SURFACE_TYPES, external_edges, external_scene, external_tessellate
from ocp_tessellate.ocp_utils import BoundingBox
from ocp_viewer_core.viewer import show

class Triangle:  # the kernel's one body
    def __init__(self, size=1.0):
        self.size = size


def tessellate(body, quality, angular_tolerance, compute_edges=True):  # step 1
    s = body.size
    return {
        "vertices": np.array([0, 0, 0, s, 0, 0, 0, s, 0], dtype=np.float32),
        "triangles": np.array([0, 1, 2], dtype=np.int32),
        "normals": np.array([0, 0, 1] * 3, dtype=np.float32),
        "edges": np.array([0, 0, 0, s, 0, 0, s, 0, 0, 0, s, 0, 0, s, 0, 0, 0, 0], dtype=np.float32),
        "obj_vertices": np.array([0, 0, 0, s, 0, 0, 0, s, 0], dtype=np.float32),
        "face_types": np.array([SURFACE_TYPES["Plane"]], dtype=np.int32),
        "edge_types": np.array([CURVE_TYPES["Line"]] * 3, dtype=np.int32),
        "triangles_per_face": np.array([1], dtype=np.int32),
        "segments_per_edge": np.array([1, 1, 1], dtype=np.int32),
    }


def discretize_edges(edges, deviation=0.1, edge_accuracy=None):  # step 2
    pts = np.array(edges, dtype=np.float32)  # here an edge is a pair of points
    return {
        "edges": pts.ravel(),
        "segments_per_edge": np.ones(len(pts), dtype=np.int32),
        "edge_types": np.full(len(pts), CURVE_TYPES["Line"], dtype=np.int32),
        "obj_vertices": pts.reshape(-1, 3).ravel(),
    }


def bounding_box(body):  # step 3
    s = body.size
    return BoundingBox({"xmin": 0, "xmax": s, "ymin": 0, "ymax": s, "zmin": 0, "zmax": 0})


def _cache_id(body):  # step 4a: the geometry, not the object
    return f"triangle-{body.size}"


def convert(obj, name, color=None, alpha=None):  # step 4
    if isinstance(obj, list) and obj and isinstance(obj[0], Triangle):
        return OcpGroup([convert(o, f"Triangle({i})", color, alpha) for i, o in enumerate(obj)], name=name)
    if isinstance(obj, Triangle):
        return external_tessellate("face", name, obj, tessellate, bounding_box(obj),
                                   cache_id=_cache_id(obj), color=color, alpha=alpha)
    if isinstance(obj, tuple) and len(obj) == 2:  # an edge: two points
        return external_edges(name, [obj], discretize_edges, color, alpha)
    raise TypeError(f"cannot show a {type(obj).__name__}")


def triangle_show(*objects, names=None, colors=None, alphas=None, **kwargs):  # step 5
    scene, names, colors, alphas = external_scene(objects, convert, names, colors, alphas)
    return show(*scene, names=names, colors=colors, alphas=alphas, **kwargs)


triangle_show(Triangle(2), ((0, 0, 1), (2, 2, 1)), names=["tri", "edge"], reset_camera="reset")
```

## 4. What to test

`tests/test_external_objects.py` tests the pipeline's side with such a kernel: the object is meshed by its own `tessellate` with the viewer's `deviation` and `angular_tolerance`, edge leaves get `deviation` and `helper_scale`, the parts come out as shapes, edges and vertices with the right fields and an identity location, the group's bounding box spans everything, no external object is in the mapping, a mixed scene keeps the OCCT objects measurable with correct refs, colors default per kind, a copy keeps the callables, and the constructor refuses an incomplete object.

For a real kernel, add on the plugin's side: its box against the OCCT box as a set of (vertex, normal) pairs, which must be identical, and the layout invariants of step 1 on curved bodies (normals aligned with vertices, indices in range, sums of `triangles_per_face` and `segments_per_edge` matching the buffers, winding agreeing with the normals, contiguous disjoint vertex blocks per face, every edge polyline within its deviation of the curve). For a `to_occt`, compare the converted bodies with the kernel's own: face counts, volumes and areas, validity (`BRepCheck_Analyzer`), and the lengths of converted edges.

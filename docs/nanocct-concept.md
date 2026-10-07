# Dual backend: OCP and nanocct

Status: agreed concept (2026-10-06), reworked for 4.0.0: ocp_tessellate hides the bindings completely (section 3.0). Steps 1–8 of section 9 are implemented on branch `nanocct` (steps 1–6 committed; the native-tessellator removal also in ocp-viewer-core, ocp_viewer, vscode-ocp-cad-viewer, jupyter-cadquery and build123d-studio). ocp-tessellate runs on OCP only, nanocct only, and both.

## 1. Requirements

- ocp-tessellate supports both bindings of OCCT: [OCP](https://github.com/cadquery/OCP) (7.x and 8.x, as today) and [nanocct](https://github.com/bernhard-42/nanocct) (OCCT 8.0.1).
- A function or method that receives an OCP or nanocct object works with that binding.
- A function or method that receives no OCP or nanocct object uses OCP, as today, unless nanocct is the only binding installed or the process-wide setting `ocp_tessellate.prefer_nanocct(True)` was made. (The first concept gave these functions a keyword-only `use_nanocct: bool = False`; the rework for 4.0.0 replaced it, see section 3.0.)
- Three installations are supported: OCP only, nanocct only, both. Neither binding is assumed to be installed.
- The public API surface stays the same, except for the deliberate removals in section 7, the OCCT classes, which ocp_tessellate no longer exports since the rework for 4.0.0 (section 3.0), and one addition, `ocp_tessellate.prefer_nanocct`. Every signature is the one of 3.x.
- `ocp_utils.py` may become a package `ocp_utils/` with the same behaviour and the same API, grouped logically.
- `NativeTessellator`, `NATIVE`, the native-tessellator toggles and every use of `ocp_addons` are removed (ocp_addons is dead). `Tessellator` becomes dual backend; its nanocct path uses nanocct's C++ helpers, which replace what the native tessellator did.

## 2. Evidence the concept rests on

All measured on macOS arm64.

| Question | Result | How it was checked |
|---|---|---|
| Where do OCP and nanocct code differ for ocp-tessellate? | The nanocct port of 3.5.3 (`nanocct-tests/patches/ocp_tessellate-3.5.3.patch`, 714 lines) changes imports, the `TopoDS` downcasts, the collection types, `BRep_Tool.Curve_s`, `gp_Pnt.Coord()`, the bounding box, `BinTools.Write_s`, `TDF_LabelSequence`, `occt_version`, `hash_compat` and the tessellator hot loops. Nothing else. | reading the patch |
| Can OCP and nanocct live in one process? | Yes, with OCP 7.9.3.1 and with OCP 8.0.1.0: both build, mesh and measure a box (volume 6.0 each). | script run in `~/.uv-global/ocp79-vtk` and `~/.uv-global/ocp80-vtk` with nanocct on `PYTHONPATH` |
| What happens on mixing? | An OCP shape passed to a nanocct function raises `TypeError: incompatible function arguments`. | same script |
| How is the binding of an object recognised? | `type(s).__module__` is `OCP.OCP.TopoDS` for OCP and `nanocct.TopoDS` for nanocct; the classes are unrelated, `isinstance` across bindings is `False` both ways. | same script |
| Cost of a per-call binding lookup | ~10 ns for a dict keyed by `type(obj)` | `timeit`, system Python |
| Import cost (warm) | `import OCP` 0.28–0.29 s, which covers every OCP module ocp-tessellate uses. `import nanocct` 0.001–0.003 s; the 32 nanocct modules ocp-tessellate uses (incl. `NCollection`) 0.18–0.20 s. | three runs in `ocp80-vtk` |
| Can the three installation cases be simulated in one environment? | Yes: `sys.modules["OCP"] = None` (or `"nanocct"`) makes the import raise `ImportError`. | script, all four combinations |
| Call sites that can be unified instead of shimmed | `(p.X(), p.Y(), p.Z())` works in OCP 7.9, OCP 8.0 and nanocct (nanocct's `Coord()` returns a `gp_XYZ`); `Bnd_Box.CornerMin()`/`CornerMax()` exist in all three (`GetXMin` is missing in OCP 7.9). | probe script in all three |
| Call sites that need a shim | `BRep_Tool.Curve_s(edge, loc)`: OCP needs 4 arguments, nanocct takes 2 and returns a tuple. | same probe script |
| Tessellator speed (torus, `Tessellator.compute` incl. meshing, best of 3) | quality 0.01: OCP 145 ms, nanocct 107 ms; quality 0.002: OCP 453 ms, nanocct 390 ms; identical vertex and triangle counts. The extraction part alone was not measured separately. The native tessellator was not measured (`ocp_addons` is not installed). | OCP: working copy in `ocp80-vtk`; nanocct: patched 3.5.3 in `nanocct-tests/.venv` |
| How does ty treat a kernel chosen at runtime? | A value typed `ModuleType` gives `Unknown` for every attribute and no error, not even for a missing name. ty checks a module against a `Protocol`, but rejects plain members ("does not accept writes"), and `@property` members collide with the class names in their own annotations. | probe package checked with ty 0.0.81 |
| What does downstream import? | ocp-viewer-core and jupyter-cadquery import ~60 names from `ocp_utils`, `convert`, `tessellator` (incl. `tessellator.get_faces`, `tessellator.NATIVE`), so module-level names are public API. | AST scan of ocp-viewer-core, vscode-ocp-cad-viewer, build123d, cadquery, bd_warehouse, jupyter-cadquery |

Not verified: whether OCP and nanocct coexist in one process on Linux and Windows.

## 3. Architecture

### 3.0 The rework for 4.0.0: the bindings are hidden

The first implementation of step 7 kept a "default kernel" and re-exported its OCCT classes from the modules (`_kernel/default.py`). The rework drops that, which makes 4.0.0 a breaking release:

- No module exports OCCT classes any more (`ocp_utils.TopoDS_Shape`, `tessellator.gp_Pnt`, `ocp_utils.downcast_LUT`, the `TopTools` maps, `hash_compat`, ...). An AST scan of ocp-viewer-core, ocp_vscode, ocp_viewer, jupyter-cadquery, build123d-studio, build123d, cadquery, bd_warehouse and the nanocct ports found no import of an OCCT name from ocp_tessellate, and none of the test modules used one through `import *`. The API test treats every snapshot entry of kind "occt" as removed and fails if a module exposes an OCCT object again.
- Every module has `from __future__ import annotations`. The OCCT types of annotations are unions `OCP class | nanocct class`, defined in `types.py` under `TYPE_CHECKING` only, and imported from there under `TYPE_CHECKING`. Type aliases built from them (`ShapeLike`, `EdgeDiscretizer`, ...) moved under `TYPE_CHECKING` too; runtime generics in `types.py` use strings (`Wrapped["gp_Vec"]`).
- The binding of what no OCCT object decides is a process-wide setting, not an argument: `ocp_tessellate.prefer_nanocct(flag)`. `kernel()` returns nanocct if nanocct is the only binding installed or `prefer_nanocct(True)` was called, else OCP. `prefer_nanocct(True)` raises `ImportError` when nanocct is not installed, and anything but `True` / `False` raises `TypeError`; a failed call changes nothing. The flag `_PREFER_NANOCCT` is private and read only by `kernel()`, so no module can hold a stale copy.
- Why not a keyword argument: the first implementation gave about 20 functions a keyword-only `use_nanocct=False`. In functions that take an OCCT object or plain input (`cross`, `normalized`, `vertex`, `rect`, `line`, `circle`, `make_compound`, `ImageFace`) the object wins, so `cross(nanocct_vec, (0, 0, 1))` used nanocct although it was called with `use_nanocct=False`, and in a nanocct-only installation every default `use_nanocct=False` used nanocct. The argument was a tie-breaker named like a switch. A process uses one binding in practice (build123d on OCP or on nanocct), so one setting fits, and every signature stays the one of 3.x.
- `kernel_of(obj)` is the binding of an OCCT object and `kernel()` for anything else (tuples, None, wrappers, lists); `kernel_of_all(objs)` is the one binding of the OCCT objects in a sequence, `kernel()` if there is none, and a `TypeError` for objects of two bindings. Functions with several arguments that can be OCCT objects use `kernel_of_all` over all of them (`cross`, `line`, `circle`, `make_compound`, `make_compsolid`, `OcpWrapper`), so a tuple and an OCCT object in either order give the object's binding. `cross` returns a tuple, so the binding it computes with never leaves it.
- ocp_tessellate creates no locations of its own above the user's objects (the top group of `to_ocp` and the mates group have `loc=None`, which `can_be_cleaned_up` and `collect` treat as identity). A CAD object and its children share one binding, and lists and dicts get no location in `to_ocpgroup`, so locations of two bindings never meet: `mul_locations` raises `TypeError` if they do. `ImageFace` builds its face and its offset location in the binding of the location it gets, and in `kernel()` without one. Mixed scenes - lists, dicts and nested containers of OCP and nanocct objects - work (`tests/test_kernel.py::test_mixed_scenes`).

- The kernel of an object is its binding, the module `OCP` or `nanocct`, and the code reaches OCCT through OCCT's own package structure, which both bindings share: `k = kernel_of(shape)`, then `k.BRep.BRep_Tool.Triangulation_s(...)`, `k.gp.gp_Pnt(...)`. There is no list of OCCT names anywhere: the package of a name is its prefix before the first `_` (true for every name the code uses, `tests/test_kernel.py` checks it), and after `import OCP` / `import nanocct` the packages are attributes of the binding. What differs between the bindings and between OCP versions lives in two small adapters, `_kernel/ocp_adapter.py` and `_kernel/nanocct_adapter.py`, reached with `adapter(k)`: the downcasts, the collection classes, `coord`, `curve_of`, `bin_write`, `version`, `hash_compat` and the two tessellation loops. They import only what their own code uses (348 and 285 lines, before 516 and 452).
- The binding of an object is the top-level package of its class's module, decided once per class and cached (`_BY_TYPE`, also for classes that are not OCCT). Only the object itself counts: an earlier version also unwrapped `.wrapped` and took the first OCCT element of a list or tuple; a measurement over the whole suite showed that the unwrapping was used only by the predicates, where it was useless (they then test the wrapper itself), and the list scan only by `make_compound`, `make_compsolid`, `OcpWrapper` and `cross`, which now use `kernel_of_all`. Cost: over the whole suite 23 classes; a cached lookup costs 22 ns per call, and a tessellation of the RC buggy STEP model (1.6 million nodes, 2.35 million triangles) makes 35,267 (nanocct) to 68,638 (OCP) lookups, under 2 ms in all. The node and triangle loops make none. The cache was kept on purpose: a full `kernel_of` costs 28–29 ns with it and 36–37 ns (nanocct) / 54–57 ns (OCP) with a `startswith` test of the module instead (nanocct8-ocp8, 2026-10-06), about 2 ms more for that model.
- Predicates follow `k = binding_of(obj); return k is not None and isinstance(obj, k.TopoDS.TopoDS_Face)`; `binding_of` returns None for anything that is not OCCT. The ~40 `isinstance` checks of the shared code use these predicates (private ones for `gp_Pnt`, `gp_Dir`, `Geom_Plane`, `Quantity_ColorRGBA`); `ANY` is gone.

Sections 3.2 to 3.6 describe the first implementation where they differ from this.

### 3.1 Kernel modules

A private package `ocp_tessellate/_kernel/`:

- `ocp_adapter.py`: every `from OCP.… import …` as plain top-level imports, the existing OCP 7 / OCP 8 branches, and the binding-specific helpers.
- `nanocct_adapter.py`: the same names from nanocct, and the same helpers implemented for nanocct.
- `__init__.py`: the `HAS_*` flags, the dispatch, the `ANY` isinstance tuples.

Every kernel module lists its names in `__all__`; `tests/test_kernel.py` checks that `__all__` covers every public name of `ocp_adapter.py`, and in step 7 that both kernels list the same names. The kernel is typed `ModuleType`, so ty does not check `k.Name` (section 2: a `Protocol` over ~100 names that need union types for two bindings costs more than it gives); the contract test replaces that check.

Implemented: `_kernel/__init__.py`, `_kernel/ocp_adapter.py`, `_kernel/nanocct_adapter.py`. (`_kernel/default.py`, the default kernel's names for re-export, existed until the rework for 4.0.0.)

Helpers each kernel provides:

| Helper | OCP | nanocct |
|---|---|---|
| `curve_of(edge, loc)` | `BRep_Tool.Curve_s(edge, loc, 0.0, 0.0)` | `BRep_Tool.Curve_s(edge, loc)[0]` |
| `bin_write(shape, triangles, normals)` | `BinTools.Write_s` into `io.BytesIO` | `BinTools.Write_s(...)` returns `bytes` |
| `downcast_vertex` … `downcast_compound` | `TopoDS.X` or `TopoDS.X_s` (OCP 7 vs 8) | `nanocct.TopoDS.X` |
| `downcast_LUT` | `TopAbs_*` → downcast, keyed by the kernel's own enums | the same |
| `TopTools_IndexedMapOfShape`, `TopTools_IndexedDataMapOfShapeListOfShape` | `TopTools_*` (OCP 7) or `OCP.collections.*` (OCP 8) | `NCollection_IndexedMap[...]`, `NCollection_IndexedDataMap[...]` with `TopTools_ShapeMapHasher` |
| `TDF_LabelSequence` | `TDF_LabelSequence` (OCP 7) or `Sequence_TDF_Label` (OCP 8) | `NCollection_Sequence[TDF_Label]` |
| `coord(obj)` | `obj.Coord()` | a tuple from `X()`, `Y()`, `Z()` (nanocct's `Coord()` returns a `gp_XYZ`) |
| `version()` | `OCP.__version__` (e.g. `8.0.1.0`) | the nanocct distribution version (e.g. `8.0.1.1`): nanocct exposes no OCCT version (`nanocct.__version__` and `Standard_Version` do not exist), and its docs state no rule that ties its version to OCCT's |
| `TopoDS` | `OCP.TopoDS.TopoDS` | the module `nanocct.TopoDS` itself; of the 77 OCP names `ocp_adapter.py` imports, the only one not found under the same path in nanocct |
| `hash_compat` | `HashCode(MAX)` on 7.7, `hash` otherwise | `hash` |
| `tessellate_faces(...)`, `compute_edges(...)` | see section 4 | see section 4 |

The 10 `.Coord()` calls in shared code go through `k.coord(...)`; the other 9 sat in the tessellation loops, which moved into the OCP kernel unchanged. `CornerMin()`/`CornerMax()` replace the `Bnd_Box.Get()` (OCP 7) / `GetXMin()` (OCP 8) branches in the shared code: they exist in OCP 7.9, OCP 8.0 and nanocct and returned identical values in all 16 cases checked (box, torus, sphere, unbounded plane; normal and optimal; OCP 7.9 and 8.0).

### 3.2 Imports and the three installation cases

Only the package probe is inside `try`; the real imports are plain top-level imports in the kernel modules. Otherwise one name missing in one OCP version would also raise `ImportError` and silently set `HAS_OCP = False`.

```python
# ocp_tessellate/_kernel/__init__.py
HAS_OCP = True
try:
    import OCP
except ImportError:
    HAS_OCP = False

HAS_NANOCCT = True
try:
    import nanocct
except ImportError:
    HAS_NANOCCT = False

if HAS_OCP is False and HAS_NANOCCT is False:
    raise ImportError("ocp_tessellate needs OCP or nanocct")

if HAS_OCP is True:
    from . import ocp as ocp_kernel
if HAS_NANOCCT is True:
    from . import nanocct as nanocct_kernel
```

No lazy imports. When both bindings are installed, both are imported at `import ocp_tessellate` (cost in section 2).

The adapter modules are called `ocp_adapter.py` and `nanocct_adapter.py`, not `ocp.py` / `nanocct.py`: with the same name as the binding, a probe `import nanocct` bound `nanocct` in the `_kernel` package, and `from . import nanocct` then returned the binding instead of the adapter (a bug in the first implementation of step 7).

| | OCP only | nanocct only | both |
|---|---|---|---|
| argument from a binding | OCP | nanocct | the argument's binding |
| no OCCT argument | OCP | nanocct (the only one present) | OCP |
| no OCCT argument after `prefer_nanocct(True)` | `prefer_nanocct(True)` raises `ImportError("prefer_nanocct(True), but nanocct is not installed")` | nanocct | nanocct |
| `ANY.*` isinstance tuples | OCP classes | nanocct classes | both |
| neither installed | `ImportError` with a clear message at `import ocp_tessellate` | | |

So the kernel for a function without an OCCT object is `nanocct if not HAS_OCP or _PREFER_NANOCCT else OCP`. ocp_tessellate exports no OCCT classes in any of the cases.

### 3.3 Dispatch

```python
def kernel_of(obj) -> Kernel: ...
def kernel_of_all(objs) -> Kernel: ...
def kernel() -> Kernel: ...
def prefer_nanocct(flag: bool) -> None: ...
```

- `kernel_of` decides by the top-level package of `type(obj).__module__` (`OCP` / `nanocct`), cached per class (for classes that are not OCCT, too). It looks only at the object itself: wrappers (build123d, CadQuery) and sequences are not looked into, callers pass `.wrapped`. Functions that take several OCCT objects (`make_compound`, `make_compsolid`, `cross`, `OcpWrapper`) use `kernel_of_all(objs)`, the one binding of the OCCT objects among them, and a `TypeError` for objects of two bindings.
- An argument from a binding always wins; the setting is consulted only when no OCCT object is found. Functions that never receive an OCCT object (`ocp_color`, `tq_to_loc`, `vector`, `axis`, `loc_to_vecs`, `axis_to_vecs`, `deserialize`, `identity_location`, `occt_version`, `import_step_as_single_compound`) call `kernel()`, and `StepReader` picks its kernel once in `__init__`.
- `convert` dispatches per object. Tessellation results are numpy arrays, so OCP and nanocct objects can even be shown side by side; only operations that combine shapes (e.g. `make_compound`) fail on a mix.

Function bodies fetch the kernel once and reach every OCCT name through it:

```python
def get_faces(shape):
    k = kernel_of(shape)
    return _iter(k, shape, k.TopAbs_FACE, k.downcast_face)

def identity_location():
    return kernel().TopLoc.TopLoc_Location()
```

No signature changes: the first implementation added a keyword-only `use_nanocct` to `occt_version`, `identity_location`, `ocp_color`, `tq_to_loc`, `deserialize`, `vertex`, `vector`, `axis`, `line`, `circle`, `rect`, `normalized`, `cross`, `loc_to_vecs`, `axis_to_vecs`, `make_compound`, `make_compsolid`, `get_location`, `ImageFace`, `StepReader(...)` and `import_step_as_single_compound`; the rework removed it from all of them again (section 3.0).

### 3.4 isinstance checks

`_kernel.ANY` holds tuples of the classes of all installed bindings, e.g. `ANY.TopoDS_Face`. `is_topods_face(x)` becomes `isinstance(x, ANY.TopoDS_Face)`. The ~30 `isinstance` checks in `convert`, `cad_objects`, `tessellator` and `ocp_utils` switched to `ANY`. For the type checker, `ANY` is the OCP kernel module (`if TYPE_CHECKING: from . import ocp as ANY`), so `isinstance(x, ANY.TopoDS_Face)` narrows `x`; with a plain tuple ty lost the narrowing and reported ~40 new errors.

### 3.5 Types

`types.py` defines the 23 OCCT types used in annotations as unions under `TYPE_CHECKING`, e.g. `TopoDS_Shape: TypeAlias = _OCP_TopoDS_Shape | _NC_TopoDS_Shape`; the other modules import them from there under `TYPE_CHECKING` and use `from __future__ import annotations`. Where only one binding is installed, the other's imports are unresolved; `pyproject.toml` allows that for nanocct (`[tool.ty.analysis] allowed-unresolved-imports`).

### 3.6 Locations of two bindings

They never meet (section 3.0): ocp_tessellate creates no locations of its own above the user's objects, a CAD object and its children share one binding, and containers get no location. `cad_objects.collect`, `ImageFace` and `convert` multiply with `mul_locations`, which raises `TypeError` for locations of two bindings. The first implementation of step 7 converted between bindings instead; an experiment (no locations of our own, a strict product) showed that only `ImageFace` and the conversion test itself depended on it, and mixed lists, dicts and nested containers gave the same results as with the conversion.

## 4. Tessellator

### 4.1 Removed

- `ocp_tessellate/tessellator.py`: the `ocp_addons` import, `NATIVE`, `enable_native_tessellator`, `disable_native_tessellator`, `is_native_tessellator_enabled`, the `NATIVE_TESSELLATOR` environment variable, `class NativeTessellator`, and `_get_tesselator` (`tessellate()` creates `Tessellator` directly and always sends `"+"` to `progress`). Also the comment in `get_edges` that mentions `NativeTessellator`.
- `ocp_tessellate/types.py`: `TesselatorProtocol`, which only existed so the two tessellator classes could share an interface.
- `pyproject.toml`: `ocp_addons` in the ty comment.
- `examples/test_stl.py`: the commented-out `enable_native_tessellator()`.
- `CHANGELOG.md`: old entries stay; the new release entry states the removal.

### 4.2 One class, two backends

`Tessellator` keeps everything that is binding-neutral: meshing via `k.BRepMesh_IncrementalMesh`, the object vertices, filling in missing normals and edges, the getters and their dtypes. `Tessellator.tessellate` and `Tessellator.compute_edges` keep their signatures and call the kernel of the shape:

- `tessellate_faces(tess, faces, face_type, trace)`
- `compute_edges(tess, edges_with_faces, edge_type, trace, debug)`

They fill the `Tessellator` they are given, exactly as the methods did: the OCP kernel with lists, the nanocct kernel with numpy arrays (the buffer annotations of `Tessellator` allow both, and the OCP kernel asserts lists). `debug` is `trace.DEBUG`: the nanocct kernel walks the edges in one C++ call and iterates `edges_with_faces` only to trace them. The faces, edges and type functions are passed in, so the kernel does not import `ocp_utils` (which imports the kernel). In the OCP kernel they are the former method bodies, moved verbatim; the outputs are bit-identical to before (section 8).

| | OCP kernel | nanocct kernel |
|---|---|---|
| faces | today's Python loop, unchanged | zero-copy numpy views of `InternalNodes`, `InternalTriangles`, `InternalUVNodes`; normals by `nanocct.AddOns.Tessellator.NormalsFromSurface` on clamped UVs |
| edges | today's loop over (edge, face) pairs | `nanocct.AddOns.Tessellator.EdgeSegments` (one C++ call per shape) |
| trace | per face and per edge, as today | per face as today; per edge only when trace debugging is on, because the edge walk runs in C++ |

The nanocct code comes from the 3.5.3 patch but is ported by hand: the current `tessellator.py` adds the `faces_without_normals` bookkeeping, which the patch does not know. The nanocct face function must record it the same way, or `_compute_missing_normals` and the triangle counts per face drift apart.

## 5. `ocp_utils` as a package

Implemented (step 5). `ocp_utils/__init__.py` re-exported exactly the 213 names the API snapshot records for `ocp_utils`, including the OCCT names that `convert.py` and the tests took via `from ocp_tessellate.ocp_utils import *`; since the rework for 4.0.0 the OCCT names are gone (section 3.0). Not re-exported are imported modules (`np`, `OCP`, `OCP.TopoDS.TopoDS`, ...) and third-party helpers (`Iterable`, `cached`, ...); none of the star importers in ocp-tessellate, ocp-viewer-core, ocp_vscode, ocp_viewer, jupyter-cadquery or build123d uses them (AST check), and no code imports a private (`_`) name from `ocp_utils`.

The modules form an import DAG in this order; a module imports only from modules listed before it:

| Module | Contents |
|---|---|
| `compat` | the OCP version differences: `_Vertex` … `_Compound` (TopoDS downcasts), `TopTools_IndexedMapOfShape`, `TopTools_IndexedDataMapOfShapeListOfShape`, `hash_compat`, `occt_version`. Step 6 turns this into the kernel. |
| `predicates` | `is_topods_*`, `is_toploc_location`, `is_gp_*`, `is_shape` … `is_vertex`, `is_location`, `is_wrapped`, `is_empty_compound`, `is_line`, `is_degenerated_*`, `is_closed`, `is_forward` |
| `detect` | `is_cadquery*`, `is_build123d*`, `is_vector`, `is_massembly`, `_has` (duck typing) |
| `topology` | `downcast_LUT`, `downcast`, `make_compound`, `make_compsolid`, `copy_*`, `get_tshape`, `extent_or_size`, `get_compounds` … `get_vertices`, `get_downcasted_shape`, `list_topods_compound`, `unroll_*`, `is_mixed_compound`, `get_compound_type`, `get_face_type`, `get_edge_type`, `get_surface`, `get_curve` |
| `measure` | `center_of_mass`, `center_of_geometry`, `dist_shapes`, `area`, `volume`, `end_points`, `length`, `position_at`, `tangent_at` |
| `geometry` | `vertex`, `vector`, `axis`, `rect`, `line`, `circle`, `normalized`, `cross`, `get_point`, `point`, `get_tuple`, `axis_to_line`, `get_plane`, `face_center_location`, `is_same_plane`, `is_plane_xy`, `_as_plane`, `tangent_edge_at`, `trim_infinite_edge`, `trim_infinite_face` |
| `location` | `VectorLike`, `tq_to_loc`, `loc_to_tq`, `identity_location`, `is_identity`, `relocate`, `get_location`, `mul_locations`, `copy_location`, `AxisCoord`, `get_axis_coord`, `LocationCoord`, `get_location_coord`, `loc_to_vecs`, `loc_from_gp_pln`, `axis_to_vecs`, `rotate` |
| `bbox` | `make_key`, `get_size`, `cache`, `BoundingBox`, `bounding_box`, `nested_bounding_box`, `NumpyBBox`, `np_bbox` |
| `serialize` | `ocp_hash`, `serialize`, `deserialize` |
| `color` | `is_ocp_color`, `get_rgba`, `ocp_color` |

`tangent_edge_at` and `trim_infinite_*` sit in `geometry`, not in `measure`: they build edges and faces from `line`/`rect` and use `length`/`tangent_at`/`area`, so `geometry` depends on `measure` and not the other way round.

The split was generated from the original file by line ranges: the 153 top-level definitions are the same, all 138 functions and classes have an AST identical to the original, and each module imports exactly the names it reads from module scope. The old `# %%` section headers were dropped; other comments moved with their code. The moved code was not reformatted (the original is not black-clean either). `ruff --select F` reports only the two `TopTools` aliases in `compat` as unused: they exist to be imported by `topology` and `__init__`.

## 6. Public API guard

Before any change, a test records for `ocp_tessellate`, `ocp_utils`, `convert`, `tessellator`, `cad_objects` and `stepreader`:

- `dir(module)`
- `inspect.signature` of every public callable

Afterwards the only allowed differences are the deliberate removals of section 7, the OCCT names (section 3.0) and the deliberate addition `ocp_tessellate.prefer_nanocct` (`DELIBERATE_ADDITIONS`; it is defined in `_kernel`, so `KERNEL_API` makes the test describe it although it ignores `_kernel` otherwise). Signatures must match the snapshot exactly.

## 7. Deliberate removals and downstream changes

Removed from ocp-tessellate's API: `NATIVE`, `enable_native_tessellator`, `disable_native_tessellator`, `is_native_tessellator_enabled`, `NativeTessellator`, `TesselatorProtocol`.

### 7.1 ocp-viewer-core

| Where | Change |
|---|---|
| `ocp_viewer_core/tessellator.py:41` | remove `from ocp_tessellate.tessellator import NATIVE` |
| `ocp_viewer_core/tessellator.py:44-95` | remove `NATIVE_TESSELLATOR_AVAILABLE`, `ENV_VAR`, the four toggles and their `__all__` entries |
| `ocp_viewer_core/tessellator.py:1-20` | rewrite the module docstring; the module keeps only the `ImageFace` re-export |
| `ocp_viewer_core/show.py:866, 1282, 1509, 1693` | the `progress` default of `show`, `show_object`, `remove_object`, `show_objects` becomes `"-+c"` (the `"*"` mark is never emitted any more; `Progress.update` prints a mark only if it is in the string, so a user string with `"*"` keeps working) |
| `ocp_viewer_core/show.py:958-961, 1385-1388, 1773-1776` | the docstrings: default `"-+c"`, the `"*"` line ("tessellated with native code") removed |
| `CHANGELOG.md` | new "Python (unreleased)" entry |
| `pyproject.toml:50`, `pyproject.toml:7` | pin and version: decided at release time, see 7.5 |

### 7.2 ocp_vscode (`vscode-ocp-cad-viewer`)

| Where | Change |
|---|---|
| `ocp_vscode/__init__.py:30-33` | remove the four toggle imports (`ImageFace` stays) |
| `ocp_vscode/__init__.py:54-55, 67-68` | remove their `__all__` entries |
| `ocp_vscode/__init__.py:117-118` | remove `init_native_tessellator()` and its print |
| `Makefile:1-3, 93-97` | remove `NATIVE_TESSELLATOR=0` from `tests`, remove the `native_tests` target and its `.PHONY` entry |
| `CHANGELOG.md` | new "Unreleased" entry |
| `pyproject.toml:31`, `pyproject.toml:7` | pin and version: decided at release time, see 7.5 |

The repository has uncommitted changes that are not part of this work (`.vscode/settings.json`, `examples/box.py`, untracked `ocp_vscode/static/`); they stay untouched and are not staged.

### 7.3 ocp_viewer

| Where | Change |
|---|---|
| `ocp_viewer/__init__.py:53-56` | remove the four toggle imports |
| `ocp_viewer/__init__.py:88-89, 99-100` | remove their `__all__` entries |
| `ocp_viewer/__init__.py:131-132` | remove `init_native_tessellator()` and its print |
| `CHANGELOG.md` | new "Unreleased" entry |
| `pyproject.toml:28`, `pyproject.toml:7` | pin and version: decided at release time, see 7.5 |

### 7.4 jupyter-cadquery

Not changed. Its native block (`jupyter_cadquery/__init__.py:66-84`) is inside a bare `try`/`except` and becomes dead code.

### 7.5 Release order

Each publish needs an explicit go, and every pin change needs approval.

1. ocp-tessellate 3.6.0
2. ocp-viewer-core
3. ocp_vscode and ocp_viewer

Constraints found while implementing, which decide the version numbers of 2. and 3.:

- ocp-viewer-core's Python and JavaScript halves must agree on major.minor (`ocp-viewer-core/Development.md:7`); a minor bump is a minor bump of both halves (`Development.md:19`). A Python 1.1.0 therefore implies a JavaScript 1.1 release.
- A patch release of ocp-viewer-core (1.0.14) cannot remove the toggles: ocp_vscode (`>=1.0.11,<1.1.0`) and ocp_viewer (`>=1.0.10,<1.1.0`) would resolve to it and fail at import.
- The VS Code extension compares its own version with the `ocp_vscode` library at major.minor (`ocp-viewer-core/Development.md:29`), so an ocp_vscode 4.2.0 implies an extension 4.2.
- ocp-viewer-core's new code no longer imports `NATIVE`, so it works with ocp-tessellate 3.5.x and 3.6.x; its pin `ocp-tessellate>=3.5.0,<3.6.0` only has to be widened.

The existing pins keep every published combination working until the next package is released.

## 8. Testing

- Existing suite, OCP only: `~/.uv-global/ocp79-vtk/.venv` (OCP 7.9.3.1) and `~/.uv-global/ocp80-vtk/.venv` (OCP 8.0.1.0). Run with `<venv>/bin/python -m pytest tests/ -q`; never a bare `pytest` at the repository root (it collects `examples/` and hangs).
- nanocct only: `~/.uv-global/nanocct8/.venv` (nanocct 8.0.1.1, no OCP).
- Both: `~/.uv-global/nanocct8-ocp8/.venv` (nanocct 8.0.1.1 and OCP 8.0.1.0 with VTK). In both nanocct venvs build123d, cadquery, ocpsvg, ocp_gordon and bd_materials are the nanocct ports from `nanocct-tests/sources`, and the five viewer-side packages are editable installs of the working copies.
- Kernel tests (`tests/test_kernel.py`, step 6): only `_kernel/` imports OCP; outside the kernel no OCCT name is used in a function body (annotations and re-exports only); `__all__` of `ocp_adapter.py` lists every public name; `kernel_of`, `kernel` and `ANY` behave as in section 3.3. Step 7 adds: both kernel modules expose the same names.
- Installation-case test: one subprocess per case with `sys.modules["OCP"] = None` and/or `sys.modules["nanocct"] = None`, checking the `HAS_*` flags, the default binding, `prefer_nanocct(True)` (nanocct, or its `ImportError` without nanocct) and the import error when neither is installed.
- Equivalence test: the same shapes (box, torus, a face with a parametric singularity, a located face, a reversed face) tessellated with OCP and with nanocct in one process; all getters compared (vertices, triangles, normals, UVs, edges, per-face and per-edge counts).
- ty: `<venv>/bin/ty check --python <venv> ocp_tessellate tests/typing_conformance.py`.
- ocp79-vtk pins build123d 0.12.0 and cadquery 2.8.0, because build123d `dev` is OCP-8-only. Expected: ocp79-vtk 200 passed, 5 skipped (BuildSheet); ocp80-vtk 205 passed.
- ocp-viewer-core, ocp_vscode, ocp_viewer: their own suites. In both venvs all four packages are editable installs of the working copies. Host suites run with `OCP_VSCODE_PYTEST=1 OCP_VIEWER_PYTEST=1` (ocp_vscode) or `OCP_VIEWER_PYTEST=1` (ocp_viewer); ocp-viewer-core's own suite runs without them, because `OCP_VIEWER_PYTEST=1` switches the core into its pytest mode and fails 8 of its tests. ocp_vscode's `tests/test_viewer_config.py` drives the viewer running on port 3939: never run two of these suites in parallel (two parallel runs produced 16 bogus failures; sequential runs pass).
- ocp79-vtk must have the VTK build of OCP active: build123d 0.12.0 pulls `cadquery-ocp-novtk`, which overwrites `OCP/` and breaks cadquery 2.8.0 (`IVtkOCC_Shape` missing). It happened again on 2026-10-06 after jupyter-cadquery was installed editable; check the size of `OCP/OCP.cpython-313-darwin.so` (VTK build 147,968,960 bytes, novtk 147,173,440).
- The API test ignores what the private package `ocp_tessellate._kernel` defines (`kernel_of`, `kernel`, ...), even where a public module imports it, except `prefer_nanocct` (`KERNEL_API`).
- `prefer_nanocct` is process-wide: `tests/conftest.py` resets it to `False` before and after every test (autouse fixture).

Results after steps 1–4 (2026-10-06, all suites sequential, both venvs with editable installs and the VTK build of OCP):

| Suite | ocp79-vtk | ocp80-vtk |
|---|---|---|
| ocp-tessellate | 200 passed, 5 skipped (BuildSheet) | 205 passed |
| ocp-viewer-core | 85 passed | 83 passed, 2 failed (`test_materials.py` emissive under OCP 8, same without the changes) |
| ocp_vscode | 132 passed | 132 passed |
| ocp_viewer | 78 passed | 78 passed |

Results after step 6 (2026-10-06, all suites sequential, both venvs with editable installs and the VTK build of OCP):

| Suite | ocp79-vtk | ocp80-vtk |
|---|---|---|
| ocp-tessellate | 214 passed, 5 skipped (200 + 14 kernel tests; BuildSheet skipped) | 219 passed (205 + 14 kernel tests) |
| ocp-viewer-core | 85 passed | 83 passed, 2 failed (emissive, known) |
| ocp_vscode | 132 passed | 132 passed |
| ocp_viewer | 78 passed | 78 passed |

- ty on both venvs: only the known diagnostics (`CadquerySketch._tags`, and `BuildSheet` on ocp79-vtk).
- Bit-identical outputs: box, torus, sphere, cylinder, filleted box, moved and rotated torus, reversed box; `tessellate()` without UVs, with normalized and with raw UVs; `bounding_box`; `discretize_edge`: 35 results, 217 arrays, 456,720 values, identical in dtype, shape and value to commit 506e2fe, on OCP 7.9 and 8.0.
- Speed (ocp80-vtk, medians of 5, two rounds): a 400-part build123d assembly through `to_ocpgroup` + `tessellate_group` 734–747 ms before, 743–751 ms after; a torus at quality 0.002 460–461 ms before, 440–442 ms after.

Results after steps 7–8 and the rework for 4.0.0, including `prefer_nanocct` (2026-10-06, sequential):

| Suite | ocp79-vtk | ocp80-vtk | nanocct8 | nanocct8-ocp8 |
|---|---|---|---|---|
| ocp-tessellate | 236 passed, 42 skipped | 241 passed, 37 skipped | 191 passed, 37 skipped (without `test_cadquery.py`, `test_color.py`: cadquery is not installed there) | 287 passed |
| ocp-viewer-core | 85 passed | 83 passed, 2 failed (emissive, known) | – | – |
| ocp_vscode | 132 passed | 132 passed | – | – |
| ocp_viewer | 78 passed | 78 passed | – | – |

- Skipped where only one binding is installed: the 31 equivalence tests, the mixed-scene tests and the test that locations of two bindings do not mix; on ocp79-vtk also the 5 BuildSheet tests.
- In nanocct8 and nanocct8-ocp8 build123d and cadquery are the nanocct ports, so test_build123d.py and test_cadquery.py run through the nanocct kernel there.
- `tests/test_kernel.py` (51 tests where both are installed): only the adapters and the probes import a binding at runtime, each only its own, and outside them only `types.py`, under `TYPE_CHECKING`; names imported under `TYPE_CHECKING` are used in annotations only; every `k.<package>.<Name>` the code writes follows the package rule and exists in every installed binding; both adapters define every `adapter(k).<name>` the code uses (statically, so in every venv); no OCCT names are exported; flags, `kernel()`, `prefer_nanocct` (public, takes only a bool, raises without nanocct), `kernel_of` of anything that is not OCCT gives `kernel()`, an OCCT object keeps its binding whatever the preference, `cross` / `normalized` / `line` / `circle` / `vertex` / `rect` take the binding of any OCCT argument and `kernel()` for plain input, `ImageFace` with and without a location, dispatch per installed binding, predicates per binding, `make_compound` of a generator, mixed scenes (list, dict, nested), locations of two bindings raise, and the four installation cases in subprocesses that hide `OCP` and/or `nanocct`. The structural tests were checked with deliberate violations (a missing name, a name under the wrong package, a missing adapter function, a runtime use of a type-only name, an exported OCCT object): each is reported.
- `tests/test_api_surface.py`: every OCCT name of the snapshot is gone, and no module exposes an OCCT object; `annotations` and `TYPE_CHECKING` are not part of the surface.
- `tests/test_binding_equivalence.py` (where both are installed): 9 shapes (box, torus, sphere, cylinder, filleted box, moved torus, reversed box, mesh-only face, a compound of a mesh-only face and a sphere) × 3 UV modes, plus discretized edges. BRepMesh does not mesh bit-identically in OCP 8.0.1.0 and nanocct 8.0.1.1 (both deterministic, same counts, different nodes for a torus), so each shape is meshed with OCP and transferred with its triangulation (`serialize`, then `deserialize` after `prefer_nanocct(True)`). On the same mesh all 261 arrays of the two kernels are bit-identical.
- The OCP path is still bit-identical to commit 506e2fe (35 results, 217 arrays, OCP 7.9 and 8.0).
- ty: `pyproject.toml` allows the nanocct imports to be unresolved where nanocct is not installed (`[tool.ty.analysis] allowed-unresolved-imports`). On ocp79-vtk and ocp80-vtk only the known diagnostics remain. ty from ocp80-vtk run with `--python` against nanocct8 and nanocct8-ocp8 reports no error in the nanocct adapter and the shared code; the OCP imports of `_kernel/ocp_adapter.py` and `types.py` show as missing there, because those venvs have no OCP stubs (nanocct8-ocp8) or no OCP (nanocct8).
- Speed in nanocct8-ocp8 (medians of 5), raw shapes of each binding: 400 parts (box minus cylinder) through `to_ocpgroup` + `tessellate_group`: OCP kernel 674–699 ms, nanocct kernel 342–354 ms over all rounds before and after the rework; torus at quality 0.002 (meshing included): 433–443 ms and 352–359 ms.

## 9. Order of work

Each step is its own commit; each commit waits for an explicit go.

1. API snapshot test, listing the deliberate removals of section 7.
2. Remove the native tessellator from ocp-tessellate (section 4.1). Tests green on OCP 7.9 and 8.0.
3. Remove it from ocp-viewer-core (section 7.1).
4. Remove it from ocp_vscode and ocp_viewer (sections 7.2, 7.3); run their tests against the local ocp-viewer-core and ocp-tessellate.
5. Split `ocp_utils` into the package (section 5); a pure move, checked by the snapshot.
6. Add `_kernel/__init__.py` with the `HAS_*` flags and `_kernel/ocp_adapter.py`; route all code through the kernel, including the OCP `tessellate_faces` / `compute_edges`. OCP-only tests green on 7.9 and 8.0. (Done.)
7. Add `_kernel/nanocct_adapter.py`, nanocct in the dispatch, `use_nanocct` (replaced by `prefer_nanocct` in the rework, section 3.0), the nanocct `tessellate_faces` / `compute_edges` (hand-ported, section 4.2), and the installation-case test. (Done.)
8. Run all tests against both kernels, plus the equivalence test. (Done.)

## 10. Open points

- Release versions and pins of ocp-viewer-core, ocp_vscode and ocp_viewer (constraints in 7.5).
- ocp-viewer-core and the viewers still import OCP themselves (e.g. ocp-viewer-core's selectors, measure and materials); a nanocct-only environment needs them to go through ocp_tessellate or a kernel of their own. Not part of this concept yet.
- A nanocct pin in ocp-tessellate's `pyproject.toml` (like OCP, nanocct is not a declared dependency today).
- Linux and Windows: coexistence of OCP and nanocct in one process is only verified on macOS; CI on Linux would settle it.

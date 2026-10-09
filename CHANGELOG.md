## v3.6.0 (unreleased)

**Features**

- nanocct support: ocp_tessellate runs on OCP, on nanocct, or on both installed side by side. An OCP or nanocct object - or the build123d / CadQuery object wrapping it - is handled with its own binding, so OCP and nanocct objects can be shown together in one list or dict. With nanocct the tessellation runs on numpy views of the triangulation and nanocct's C++ helpers (about twice as fast for many small parts); on the same mesh both bindings give identical results. Functions that get no OCCT object (`identity_location`, `tq_to_loc`, `vector`, `axis`, `deserialize`, `ocp_color`, `occt_version`, `StepReader`, `import_step_as_single_compound`, and `vertex`/`line`/`circle`/`rect`/`normalized`/`cross`/`make_compound`/`ImageFace` given only tuples, an empty list or no location) use OCP, as before; nanocct when it is the only binding installed, or where both are installed when the environment variable `OCCT_BINDING=nanocct` is set (`OCP` or `nanocct`; read once at import, for the whole process; another value, or a binding that is not installed, raises `ImportError` at import). It does not change the binding of OCCT objects, and it is the variable the other libraries of the ecosystem are meant to read too. No signature changes

- OCCT helpers for viewers, dual binding, in `ocp_utils`: `face_normal`, `closest_directions` (tangents of edges and normals of faces at their closest points), `angle_between`, and `vis_material_values` / `make_vis_material` (an `XCAFDoc_VisMaterial` as plain values and back, `VisMaterialValues`, `ALPHA_MODES`). They carry the OCCT side of ocp-viewer-core's measurements and materials, which imports no binding any more. The emissive factor of a material is read and written on OCP 7.9 and nanocct; OCP 8 does not bind it

- `center_of_mass` measures a shape by its highest dimension: the volume of its solids, else the area of its faces, else the length of its edges, else the mean of its vertices. It used volume properties for everything but a face, so a vertex, an edge and a compound of faces, edges or vertices came out at the origin (or at the origin of their location); wires and shells were right only by accident. Solids, faces and compounds of solids give the same values as before

- `ocp_utils.to_ocp(obj)` and `ocp_utils.to_nanocct(obj)` convert OCCT objects between the bindings, where both are installed: shapes (in OCCT's binary BRep format with triangulations and normals, in the newest format version both bindings know, so an older OCCT reads what a newer one writes), points, vectors, directions, coordinates, transformations, locations, axes, planes and colors. An object of the target binding is returned as it is; other types raise `TypeError`. The results are copies: shapes converted one by one no longer share sub-shapes

- `python_enumeration` parameter of `OcpConverter` and `to_ocpgroup` (default `False`, vscode-ocp-cad-viewer issue 242): repeated names in a group are numbered from 0 on every occurrence, `Solid(0)`, `Solid(1)`, `Solid(2)`, instead of `Solid`, `Solid(2)`, `Solid(3)`, so a list of shapes of one type shows its Python indices. It applies wherever names are made unique: lists and tuples, unrolled compounds, assemblies, location lists and the `names` argument. The counter is per name, not the position in the list, and a name that occurs once keeps no suffix. The default keeps the former names, since assembly paths are built from them

**Removals**

- OCCT classes are no longer exported: `ocp_utils`, `convert`, `tessellator`, `stepreader`, `cad_objects` and `types` re-exported the OCP classes they used (`ocp_utils.TopoDS_Shape`, `tessellator.gp_Pnt`, ...), and `ocp_utils` also `downcast_LUT`, `hash_compat` and the `TopTools` map classes. ocp_tessellate now hides the binding; import OCCT classes from OCP or nanocct directly
- The native tessellator is removed: `NativeTessellator`, `NATIVE`, `enable_native_tessellator()`, `disable_native_tessellator()`, `is_native_tessellator_enabled()` and the `NATIVE_TESSELLATOR` environment variable are gone, and `ocp_addons` is no longer used. `tessellate()` always uses `Tessellator`. `TesselatorProtocol` is removed with it, since it only existed so that the two tessellator classes could share an interface

**Changes**

- `StepReader` works with nanocct: it read names with OCP's out-parameter convention of `TDF_Label.FindAttribute` (nanocct returns `(found, attribute)`), so loading failed. All its methods use the binding it was created in, and `to_build123d` raises a `TypeError` that names the `OCCT_BINDING` to start Python with when build123d wraps the other binding. `tests/test_stepreader.py` covers names, colors, locations, nested assemblies and `to_build123d` per binding
- `is_same_plane` raises a `TypeError` for planes of two bindings
- ty: where both bindings are installed, the OCP | nanocct unions of the annotations cannot express that values share one binding; these sites carry a `ty: ignore` with the reason (a known limit)
- `BoundingBox` raises `TypeError` instead of `ValueError` for an argument of the wrong type
- The code passes ruff's default rules (`ruff check`, ruff 0.16); `pyproject.toml` only sets `combine-as-imports`. Two tests that were defined twice under one name, and so never ran, run again, and two cache tests tessellate a group with its own instances
- `ocp_tessellate.ocp_utils` is a package now, grouped by topic (`compat`, `predicates`, `detect`, `topology`, `measure`, `geometry`, `location`, `bbox`, `serialize`, `color`). Every function, class and value of the former module is still importable from `ocp_tessellate.ocp_utils`, and the star import gives the same names, except the OCCT classes (see above), imported modules (`np`, `OCP`, ...) and third-party helpers
- ocp_tessellate reaches OCCT through internal kernels (`ocp_tessellate._kernel`), the only places that import OCP or nanocct. Tessellation, bounding boxes and all other results are unchanged (compared bit for bit). Bounding boxes are read with `Bnd_Box.CornerMin()`/`CornerMax()` on every OCP version, which return the same values as the former `Get()` / `GetXMin()` branches

**Fixes**

- An object whose `is_empty` attribute is true is converted to the `(empty)` placeholder like an empty list

## v3.5.3

**Fixes**

- STL imports showed as the empty placeholder vertex with `Info: Ignoring degenerated face of 'Face' (no surface)`. Since 3.5.0 a face without a surface was taken for an OCCT artifact, but a mesh-only face - `import_stl` produces one - has no surface by construction and carries its geometry as a triangulation. A face is degenerate only when it has neither

## v3.5.2

**Changes**

- numpy 2 is required (`numpy>=2.0`)

**Fixes**

- A cadquery sketch that is all construction geometry, e.g. `rect(..., mode="c")`, showed nothing: cadquery files construction under `_tags` and leaves the faces compound empty, so the converter found none of its three sources and produced a group with no objects. The tagged shapes are drawn now, as a `Construction` object, when nothing else was collected

## v3.5.1

**Features**

- build123d's `BuildSheet` (build123d PR #1434) is converted like the other builders: the reference `Shell` becomes a single face object named `Shell`, with a `sheet_local` sibling unless `show_locals=False`

**Changes**

- OCP 8 compatibility: on OCP 8 the `TopTools` map classes and `TDF_LabelSequence` are imported from `OCP.collections`, and bounding boxes are read through the individual `Bnd_Box` getters because `Get()` is not bound there
- The wheel no longer installs `tests` and `examples` as top-level packages

**Fixes**

- `StepReader.to_build123d` labeled the root Compound with the last child's name instead of the assembly name, because `walk()` rebound its `label` parameter in the loop
- A build123d builder with no geometry yet, e.g. a `BuildPart`, `BuildSheet`, `BuildSketch` or `BuildLine` shown from inside its own context, raised an `AssertionError`. It is now converted to the same `(empty)` placeholder as an empty list
- The result of build123d's `ShapeList.group_by` (a `GroupBy`) was silently skipped as an unknown object, so `show(b.edges().group_by(Axis.Z))` showed nothing. It is now converted to a group named `GroupBy` with one `ShapeList` group per key

## v3.5.0

**Features**

- `default_facecolor`, `default_thickedgecolor` and `default_vertexcolor` are now proper defaults beside `default_color` and `default_edgecolor`: settable via `set_defaults` and accepted as arguments by `to_ocp`, `to_ocpgroup` and `to_assembly`. Precedence is explicit argument, then `set_defaults`, then the module constants `FACE_COLOR`, `THICK_EDGE_COLOR` and `VERTEX_COLOR`, which remain as fallbacks so that code assigning them directly keeps working. Those constants, and the unused `EDGE_COLOR`, will be removed in a future major

**Fixes**

- `set_defaults` silently accepted unknown keys, typos included. The check compared a missing key against `float("nan")`, which never equals itself, so the "not a valid argument" warning could never be reached
- A `BuildPart` with joints converted with `show_locals=False, render_joints=True` produced an unnamed group (`OcpGroup('None')`) instead of a group named after the object ([#17](https://github.com/bernhard-42/ocp-tessellate/issues/17)).
- Degenerate OCCT artifacts no longer crash the converter: edges without geometry (zero length) and faces without a surface are detected via O(1) checks and ignored with an info message; zero-area faces with a valid surface are dropped by the mesher as before, avoiding any area computation ([#16](https://github.com/bernhard-42/ocp-tessellate/issues/16))
- Skipped faces and edges no longer desynchronize the parallel arrays of the wire format: `face_types` and `edge_types` were appended before the "no triangulation/polygon" skip, so they ran out of step with `triangles_per_face` and `segments_per_edge`

**Changes**

- Widen the `cachetools` constraint from `~=5.5.0` to `>=5.5.0,<8` so the pin no longer holds back consumer environments. The API surface used (`LRUCache`, `cached`, `Cache.get`) is unchanged through 7.1.7, and the test suite passes against it ([#13](https://github.com/bernhard-42/ocp-tessellate/issues/13))
- Complete typing overhaul: `ty check ocp_tessellate` is clean with no `Any`, no casts and four scoped, commented suppressions. Duck-typed build123d/CadQuery objects are described as Protocols in `ocp_tessellate.types`, verified against the real classes by `tests/typing_conformance.py`; the `is_*` predicates narrow via `TypeIs`/`TypeGuard`; `to_ocp`/`to_ocpgroup` accept `object` and let the predicates narrow. New `make typecheck` target runs the gate
- Add `typing_extensions>=4.0` as a dependency (for `NotRequired`/`TypedDict` on Python 3.10 and `TypeIs`); drop it when the floor is 3.11

**Fixes (found by the typing pass)**

- `handle_cadquery_assembly` passed a scalar to `to_ocp(alphas=...)`, a guaranteed `ValueError` for any non-None alpha on a CadQuery assembly
- `NativeTessellator.compute` did not accept the `normalize_uvs` argument `tessellate()` passes, crashing whenever the native tessellator was enabled
- `StepReader.get_shape_details` compared the `ShapeType` method instead of calling it, so the nested-compsolid warning could never fire
- `StepReader.load` with `cache_name` called the removed `load_assembly`/`save_assembly`; both now raise `NotImplementedError` with a clear message instead of `AttributeError`
- `get_location`'s `to_location` branch read the `location` attribute the preceding branch had just proven absent, always raising `AttributeError`
- `circle()` and `point()` crashed on the `gp_Pnt`/`gp_Dir` inputs their signatures promised; `is_plane_xy` passed a `gp_Pln` into a function that rejected it; a `None` location crashed the bounding-box accumulation of `tessellate_group`
- `handle_cadquery_sketch` no longer mutates the user's Sketch object during conversion

**Deprecated**

- The module constants `FACE_COLOR`, `THICK_EDGE_COLOR` and `VERTEX_COLOR`, the unused `EDGE_COLOR`, and the root re-exports `is_cadquery` and `occt_version` will be removed in 4.0.0. Use the `default_*color` parameters or `set_defaults` for the first three, and import predicates from `ocp_tessellate.ocp_utils`

## v3.4.1

**Fixes**

- Clamp UV bounds to their min and max to avoid visualisation artefacts

## v3.4.0

**Features**

- Support the new build123d builder paradigm, i.e. support `part_local`, `sketch_local` and `line_local` of build123d. Changed `show_sketch_local` to `show_locals`
- Support dict subclasses that carry locations

**Fixes**

- Fix color handling for builder objects
- Fix detection of build123d `LocationList`s
- Fix object handling for the new edges
- Propagate color into unrolled mixed compounds
- Remove surrounding `{}` from the timing message
- Type hint fixes

## v3.3.1

**Fixes**

- Fix IndexError when an instance tessellates to zero vertices

## v3.3.0

**Features**

- Add `modes` parameter to `to_ocpgroup` / `to_ocp` to control per-object face/edge selection state. Each mode is a `(state_faces, state_edges)` 2-tuple of 0/1 ints that maps directly onto `OcpObject.state_faces` / `state_edges`

**Behavior changes**

- `ShapeList` is no longer flattened into a single `OcpObject`. A `ShapeList` of N items now appears in the viewer tree as a `ShapeList` group with N children, exposing the internal structure (e.g. `b.faces()` shows each face individually)
- Tighten the wrapper-cleanup invariant: only artificial `to_ocp` accumulator wrappers are collapsed during recursion. User-meaningful groups (assembly Compounds, dict entries, named ShapeLists) are now preserved verbatim. Fixes cases where `dict → assembly → solid` was being collapsed to `dict → solid`. New `OcpGroup.can_be_cleaned_up` property captures the invariant explicitly

**Fixes**

- Rewrite the `handle_build123d_builder` helper so `BuildSketch` / `BuildLine` outputs are unified explicitly via `unify`, matching the convention that homogeneous compounds are not unrolled. Resolves a `Rectangle - Rectangle` sketch appearing as two separate face entries instead of one

## v3.2.2

- Add a `normalize_uvs` flag that allows UV coordinates to be passed through raw (unnormalized) or normalized

## v3.2.1

- Fix bug where materials for sub assemblies were lost

## v 3.2.0

- Support for material property on CAD objects
- Add instanced format to the js exporter

## v3.1.2

- Remove a debug print

## v3.1.1

- Handle TopoDS.Vector/Vector_s dynamically for supporting both OCP 7.8 and 7.9
- Add colors and alphas to export_three_cad_viewer_js
- Add rounding to color conversion to int and use sRGB for OCP colors

## v3.1.0

**Features**

- Add functionality to trim infinite edges and faces
- Treat joints as helpers on the same level in assemblies to not change hierarchy (which could break animation)
- Add nested bounding box method for objects
- Ensure compounds with wires and edges are not seen as mixed compounds

**Fixes**

- Add compounds to get_type and get_kind parameters
- Refactor `helper_scale`, `render_*`, and `show_*` parameters as instance methods. They are now provided to the OcpConverter init.
- Improve infinite objects warnings
- Skip empty meshes
- Set the cache ID from the correct object
- Set debug parameter properly throughout the codebase
- Adapt to changed color definitions of build123d
- Switch to ruff for linting and formatting

## v3.0.17

- Make get_plane more robust
- Added additional OCP functions to ocp_utils
- Adapt to API changes of build123d

## v3.0.16

- Fix the regression to have continue indented to much for the non showable case

## v3.0.15

- Move the "unknown type " warning behind "debug=True" parameter
- Replace hard coded "DEBUG" with parameter "debug"

## v3.0.14

- Fix helix regression

## v3.0.13

- Adapt to CadQuery's change in color from RGB to RGBs
- Support compound of compound of edges

## v3.0.11, v3.0.12

- Support ShapeLists of Compounds
- Support TopoDS_CompSolid

## v3.0.10

- Support both hashing algorithms of OOCT
- Minor adaptations to build123d fixes/changes
- Fix showing assemblies in lists
- Fix detection of empty objects
- Fix exporting simple STEP imports
- Renamed tests and pytests folders

## v3.0.9

- Add support for OCP 7.8.1

## v3.0.8

- Fix regression for handling cadquery wires (wire.edges() returns one edge or one compound)
- Ensure get_face_type and get_edge_type always return int (ocp_utils.py)
- Enable switch from Extent to Size (being prepared for OCCT 7.8)
- Add get_surface and get_curve to ocp_utils.py

## v3.0.7

- none / deployment issues

## v3.0.6

- Migrate to pyproject.toml
- Support latest cadquery Sketch changes

## v3.0.5

- Remove numpy-quaternion dependency to support numpy 1 and 2

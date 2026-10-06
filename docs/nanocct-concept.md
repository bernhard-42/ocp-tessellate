# Dual backend: OCP and nanocct

Status: agreed concept (2026-10-06). Steps 1–5 of section 9 are implemented on branch `nanocct` in ocp-tessellate, ocp-viewer-core, ocp_viewer and vscode-ocp-cad-viewer, not committed yet.

## 1. Requirements

- ocp-tessellate supports both bindings of OCCT: [OCP](https://github.com/cadquery/OCP) (7.x and 8.x, as today) and [nanocct](https://github.com/bernhard-42/nanocct) (OCCT 8.0.1).
- A function or method that receives an OCP or nanocct object works with that binding.
- A function or method that receives no OCP or nanocct object gets a keyword-only argument `use_nanocct: bool = False`, which keeps the current behaviour.
- Three installations are supported: OCP only, nanocct only, both. Neither binding is assumed to be installed.
- The public API surface stays the same, except for the deliberate removals in section 7.
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
| What does downstream import? | ocp-viewer-core and jupyter-cadquery import ~60 names from `ocp_utils`, `convert`, `tessellator` (incl. `tessellator.get_faces`, `tessellator.NATIVE`), so module-level names are public API. | AST scan of ocp-viewer-core, vscode-ocp-cad-viewer, build123d, cadquery, bd_warehouse, jupyter-cadquery |

Not verified: whether OCP and nanocct coexist in one process on Linux and Windows.

## 3. Architecture

### 3.1 Kernel modules

A private package `ocp_tessellate/_kernel/`:

- `ocp.py`: every `from OCP.… import …` as plain top-level imports, the existing OCP 7 / OCP 8 branches, and the binding-specific helpers.
- `nanocct.py`: the same names from nanocct, and the same helpers implemented for nanocct.
- `__init__.py`: the `HAS_*` flags, the dispatch, the `ANY` isinstance tuples.

Both kernel modules expose exactly the same set of names. A test asserts that. A `Kernel` Protocol describes the contract for ty (unverified whether ty accepts a module as an implementation of a Protocol; mypy does; fallback is a small class instance per kernel).

Helpers each kernel provides (initial list, from the 3.5.3 patch):

| Helper | OCP | nanocct |
|---|---|---|
| `curve_of(edge, loc)` | `BRep_Tool.Curve_s(edge, loc, 0.0, 0.0)` | `BRep_Tool.Curve_s(edge, loc)[0]` |
| `bin_write(shape, triangles, normals)` | `BinTools.Write_s` into `io.BytesIO` | `BinTools.Write_s(...)` returns `bytes` |
| `downcast_vertex` … `downcast_compound` | `TopoDS.X` or `TopoDS.X_s` (OCP 7 vs 8) | `nanocct.TopoDS.X` |
| `IndexedMapOfShape`, `IndexedDataMapOfShapeListOfShape` | `TopTools_*` (OCP 7) or `OCP.collections.*` (OCP 8) | `NCollection_IndexedMap[...]`, `NCollection_IndexedDataMap[...]` with `TopTools_ShapeMapHasher` |
| `LabelSequence` | `TDF_LabelSequence` (OCP 7) or `Sequence_TDF_Label` (OCP 8) | `NCollection_Sequence[TDF_Label]` |
| `version()` | `OCP.__version__` | `"8.0.1"` (nanocct has no version attribute) |
| `hash_compat` | `HashCode(MAX)` on 7.7, `hash` otherwise | `hash` |
| `tessellate_faces(...)`, `edge_segments(...)` | see section 4 | see section 4 |

Unified in the shared code instead of a helper: `(p.X(), p.Y(), p.Z())` replaces `p.Coord()` (19 call sites), `gp_Pnt(p.XYZ())` replaces `gp_Pnt(*p.Coord())`, and `CornerMin()`/`CornerMax()` replace the `Bnd_Box.Get()` / `GetXMin()` branches.

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

| | OCP only | nanocct only | both |
|---|---|---|---|
| argument from a binding | OCP | nanocct | the argument's binding |
| no OCCT argument, `use_nanocct=False` | OCP | nanocct (the only one present) | OCP, as today |
| no OCCT argument, `use_nanocct=True` | `ImportError("nanocct is not installed")` | nanocct | nanocct |
| module-level names such as `ocp_utils.TopoDS_Shape` | OCP classes | nanocct classes | OCP classes, as today |
| `ANY.*` isinstance tuples | OCP classes | nanocct classes | both |
| neither installed | `ImportError` with a clear message at `import ocp_tessellate` | | |

So `use_nanocct=False` means "OCP if installed".

### 3.3 Dispatch

```python
def kernel_of(obj, use_nanocct: bool = False) -> Kernel: ...
def kernel(use_nanocct: bool = False) -> Kernel: ...
```

- `kernel_of` unwraps `.wrapped` (build123d, CadQuery), looks at the first OCCT element of a list or tuple, and decides by `type.__module__` prefix (`"OCP."` / `"nanocct."`). The result is cached per type.
- An argument from a binding always wins; `use_nanocct` is consulted only when no OCCT object is found.
- Mixed iterables are not checked beyond the first element; the binding itself raises `TypeError` on the first foreign object.
- `convert` dispatches per object. Tessellation results are numpy arrays, so OCP and nanocct objects can even be shown side by side; only operations that combine shapes (e.g. `make_compound`) fail on a mix.

Function bodies fetch the kernel once and reach every OCCT name through it:

```python
def get_faces(shape):
    k = kernel_of(shape)
    return _iter(k, shape, k.TopAbs_FACE, k.downcast_face)

def identity_location(*, use_nanocct: bool = False):
    return kernel(use_nanocct).TopLoc_Location()
```

`use_nanocct` is always keyword-only, so no positional signature changes. It is added where no OCCT object is passed or may be passed: `occt_version`, `identity_location`, `ocp_color`, `tq_to_loc`, `deserialize`, `vertex`, `vector`, `axis`, `line`, `circle`, `rect` (tuple inputs), `make_compound` (empty list), `get_location` (identity fallback), `StepReader(...)`, `import_step_as_single_compound`.

### 3.4 isinstance checks

`_kernel.ANY` holds tuples of the classes of all installed bindings, e.g. `ANY.TopoDS_Face`. `is_topods_face(x)` becomes `isinstance(x, ANY.TopoDS_Face)`. The ~30 `isinstance` checks in `convert`, `cad_objects`, `tessellator` and `ocp_utils` switch to `ANY`.

### 3.5 Types

`types.py` defines unions under `TYPE_CHECKING`, e.g. `Shape = OCP…TopoDS_Shape | nanocct…TopoDS_Shape`; nanocct ships `.pyi` stubs. ty therefore needs both bindings in the type-check environment.

## 4. Tessellator

### 4.1 Removed

- `ocp_tessellate/tessellator.py`: the `ocp_addons` import, `NATIVE`, `enable_native_tessellator`, `disable_native_tessellator`, `is_native_tessellator_enabled`, the `NATIVE_TESSELLATOR` environment variable, `class NativeTessellator`, and `_get_tesselator` (`tessellate()` creates `Tessellator` directly and always sends `"+"` to `progress`). Also the comment in `get_edges` that mentions `NativeTessellator`.
- `ocp_tessellate/types.py`: `TesselatorProtocol`, which only existed so the two tessellator classes could share an interface.
- `pyproject.toml`: `ocp_addons` in the ty comment.
- `examples/test_stl.py`: the commented-out `enable_native_tessellator()`.
- `CHANGELOG.md`: old entries stay; the new release entry states the removal.

### 4.2 One class, two backends

`Tessellator` keeps everything that is binding-neutral: meshing via `k.BRepMesh_IncrementalMesh`, the object vertices, filling in missing normals and edges, the getters and their dtypes. The kernel is resolved once per `compute()` with `k = kernel_of(shape)`. Each kernel provides:

- `tessellate_faces(shape, compute_uvs, normalize_uvs, bbox_max_dim, trace)`
- `edge_segments(shape, trace)`

Both return the flat arrays plus the `faces_without_normals` ranges.

| | OCP kernel | nanocct kernel |
|---|---|---|
| faces | today's Python loop, unchanged | zero-copy numpy views of `InternalNodes`, `InternalTriangles`, `InternalUVNodes`; normals by `nanocct.AddOns.Tessellator.NormalsFromSurface` on clamped UVs |
| edges | today's loop over (edge, face) pairs | `nanocct.AddOns.Tessellator.EdgeSegments` (one C++ call per shape) |
| trace | per face and per edge, as today | per face as today; per edge only when trace debugging is on, because the edge walk runs in C++ |

The nanocct code comes from the 3.5.3 patch but is ported by hand: the current `tessellator.py` adds the `faces_without_normals` bookkeeping, which the patch does not know. The nanocct face function must record it the same way, or `_compute_missing_normals` and the triangle counts per face drift apart.

## 5. `ocp_utils` as a package

Implemented (step 5). `ocp_utils/__init__.py` re-exports exactly the 213 names the API snapshot records for `ocp_utils`: the own functions, classes and values, and the OCCT names that `convert.py` and the tests take via `from ocp_tessellate.ocp_utils import *`. Not re-exported are imported modules (`np`, `OCP`, `OCP.TopoDS.TopoDS`, ...) and third-party helpers (`Iterable`, `cached`, ...); none of the star importers in ocp-tessellate, ocp-viewer-core, ocp_vscode, ocp_viewer, jupyter-cadquery or build123d uses them (AST check), and no code imports a private (`_`) name from `ocp_utils`.

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

Afterwards the only allowed differences are the new keyword-only `use_nanocct` parameter and the deliberate removals of section 7.

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
- nanocct only: `nanocct-tests/.venv` with the patched build123d.
- Both: a new environment with OCP and the nanocct wheel from the GitHub release (needs approval, section 10).
- Kernel contract test: both kernel modules expose the same names.
- Installation-case test: one subprocess per case with `sys.modules["OCP"] = None` and/or `sys.modules["nanocct"] = None`, checking the `HAS_*` flags, the default binding, the `use_nanocct=True` error and the import error when neither is installed.
- Equivalence test: the same shapes (box, torus, a face with a parametric singularity, a located face, a reversed face) tessellated with OCP and with nanocct in one process; all getters compared (vertices, triangles, normals, UVs, edges, per-face and per-edge counts).
- ty: `<venv>/bin/ty check --python <venv> ocp_tessellate tests/typing_conformance.py`.
- ocp79-vtk pins build123d 0.12.0 and cadquery 2.8.0, because build123d `dev` is OCP-8-only. Expected: ocp79-vtk 200 passed, 5 skipped (BuildSheet); ocp80-vtk 205 passed.
- ocp-viewer-core, ocp_vscode, ocp_viewer: their own suites. In both venvs all four packages are editable installs of the working copies. Host suites run with `OCP_VSCODE_PYTEST=1 OCP_VIEWER_PYTEST=1` (ocp_vscode) or `OCP_VIEWER_PYTEST=1` (ocp_viewer); ocp-viewer-core's own suite runs without them, because `OCP_VIEWER_PYTEST=1` switches the core into its pytest mode and fails 8 of its tests. ocp_vscode's `tests/test_viewer_config.py` drives the viewer running on port 3939: never run two of these suites in parallel (two parallel runs produced 16 bogus failures; sequential runs pass).
- ocp79-vtk must have the VTK build of OCP active: build123d 0.12.0 pulls `cadquery-ocp-novtk`, which overwrites `OCP/` and breaks cadquery 2.8.0 (`IVtkOCC_Shape` missing).

Results after steps 1–4 (2026-10-06, all suites sequential, both venvs with editable installs and the VTK build of OCP):

| Suite | ocp79-vtk | ocp80-vtk |
|---|---|---|
| ocp-tessellate | 200 passed, 5 skipped (BuildSheet) | 205 passed |
| ocp-viewer-core | 85 passed | 83 passed, 2 failed (`test_materials.py` emissive under OCP 8, same without the changes) |
| ocp_vscode | 132 passed | 132 passed |
| ocp_viewer | 78 passed | 78 passed |

## 9. Order of work

Each step is its own commit; each commit waits for an explicit go.

1. API snapshot test, listing the deliberate removals of section 7.
2. Remove the native tessellator from ocp-tessellate (section 4.1). Tests green on OCP 7.9 and 8.0.
3. Remove it from ocp-viewer-core (section 7.1).
4. Remove it from ocp_vscode and ocp_viewer (sections 7.2, 7.3); run their tests against the local ocp-viewer-core and ocp-tessellate.
5. Split `ocp_utils` into the package (section 5); a pure move, checked by the snapshot.
6. Add `_kernel/__init__.py` with the `HAS_*` flags and `_kernel/ocp.py`; route all code through the kernel, including the OCP `tessellate_faces` / `edge_segments`. OCP-only tests green on 7.9 and 8.0.
7. Add `_kernel/nanocct.py`, the dispatch, `use_nanocct`, the nanocct `tessellate_faces` / `edge_segments` (hand-ported, section 4.2), and the installation-case test.
8. Run all tests against both kernels, plus the equivalence test.

The uncommitted changes in `ocp_tessellate/tessellator.py` and `ocp_tessellate/types.py` are committed before step 2, so that step's diff stays separate.

## 10. Open points

- Release versions and pins of ocp-viewer-core, ocp_vscode and ocp_viewer (constraints in 7.5).
- A test environment with both bindings: needs approval, because the nanocct wheel comes from the GitHub release, not from PyPI.
- Linux and Windows: coexistence of OCP and nanocct in one process is only verified on macOS; CI on Linux would settle it.

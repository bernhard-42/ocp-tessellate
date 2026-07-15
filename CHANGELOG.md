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

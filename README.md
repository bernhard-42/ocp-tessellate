# OCP-Tessellate

Tessellate [OCP](https://github.com/cadquery/OCP) (Python bindings for OpenCascade) shapes into a JSON-friendly format suitable for [three-cad-viewer](https://github.com/bernhard-42/three-cad-viewer) and downstream tooling such as [ocp_vscode](https://github.com/bernhard-42/vscode-ocp-cad-viewer).

It accepts geometry from [CadQuery](https://github.com/CadQuery/cadquery), [build123d](https://github.com/gumyr/build123d), and raw `TopoDS_*` shapes of [OCP](https://github.com/cadquery/OCP) or [nanocct](https://github.com/bernhard-42/nanocct), walks the structure, computes triangulations / discretized edges, and emits a hierarchical group of meshed instances.

## Installation

```bash
pip install ocp-tessellate
```

Requires Python 3.10+ and OCP 7.8, 7.9 or 8.0, or nanocct 8.0.1, or both.

OCP and nanocct objects are each handled with their own binding, also side by side in one scene. Where no OCCT object decides - functions given only tuples, `deserialize`, `StepReader`, ... - ocp_tessellate uses OCP, or nanocct if it is the only binding installed. With both installed, `ocp_tessellate.prefer_nanocct(True)` switches this default to nanocct for the whole process.

## Quick start

### Programmatic pipeline

For embedding in a tool (the path used by `ocp_vscode`):

```python
from build123d import Box, Sphere, Compound
from ocp_tessellate.convert import to_ocpgroup, tessellate_group

box = Box(1, 2, 3)
sphere = Sphere(0.5)
sphere.label = "ball"
assembly = Compound(label="root", children=[box, sphere])

# Step 1: convert to an OcpGroup hierarchy + instance list
group, instances = to_ocpgroup(assembly)

# Step 2: tessellate the instances
meshed_instances, shapes, mapping = tessellate_group(group, instances)
# `shapes` is a JSON-serializable tree consumable by three-cad-viewer
```

### Direct export to three-cad-viewer

The simplest path — emit a `.js` file that a [three-cad-viewer](https://github.com/bernhard-42/three-cad-viewer) page can load directly:

```python
from build123d import Box
from ocp_tessellate.convert import export_three_cad_viewer_js

box = Box(1, 2, 3)
export_three_cad_viewer_js("box", box, filename="box.js")
# writes box.js with `var box = {...}` ready for three-cad-viewer/examples
```

This is the bridge to three-cad-viewer: bundles tessellated instances + scene tree into a single JSON payload assigned to a JS variable.

## Public API

Three entry points in `ocp_tessellate.convert`:

- **`export_three_cad_viewer_js(var, *objs, names=None, colors=None, alphas=None, modes=None, filename=None, keep_instances=False)`** — runs the full pipeline (`to_ocpgroup` → `tessellate_group` → JSON encode) and writes a `var <name> = {...};` JS file. The direct integration point with [three-cad-viewer](https://github.com/bernhard-42/three-cad-viewer).
- **`to_ocpgroup(*objs, names=None, colors=None, alphas=None, modes=None, ...)`** — converts CAD objects (build123d / CadQuery / OCP / nested dicts and lists) into an `OcpGroup` hierarchy plus an instance list. Accepts per-object `names`, `colors`, `alphas`, `materials`, `modes` (`(state_faces, state_edges)` 2-tuples), and a `default_color`. Renderer-control flags include `helper_scale`, `render_joints`, `render_mates`, `show_parent`, `show_locals`.
- **`tessellate_group(group, instances, kwargs=None, progress=None, timeit=False)`** — meshes the instances and returns the structures consumed by three-cad-viewer. `kwargs` can carry tessellation parameters like `deviation`, `angular_tolerance`, `edge_accuracy`, and `render_normals`.

For lower-level use, `OcpConverter` exposes `to_ocp(...)`, which is what `to_ocpgroup` calls internally.

## What gets shown

Inputs are walked recursively. The resulting tree mirrors the input structure:

| input                                     | result                                                                                                   |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| build123d / CadQuery / OCP shape          | a single `OcpObject`                                                                                     |
| `dict`                                    | a `Dict` group with one named child per key                                                              |
| `list` / `tuple`                          | a `List` group with default-named children                                                               |
| `ShapeList`                               | a `ShapeList` group exposing each item individually                                                      |
| `Compound(children=[...])` (assembly)     | a group preserving the assembly hierarchy                                                                |
| `Compound(...)` (standard, no children)   | unwrapped to its inner shape                                                                             |
| `BuildPart` / `BuildSheet` / `BuildSketch` / `BuildLine` | a single `OcpObject` for the builder result, plus a `part_local` / `sheet_local` / `sketch_local` / `line_local` sibling unless disabled |

## Compatibility

- Python 3.10+
- OCP 7.8, 7.9 and 8.0
- nanocct 8.0.1
- build123d (current)
- CadQuery 2.x

## Test coverage

The suite runs in each of the three installations, OCP only, nanocct only and both, and what it skips depends on the installation, not on failures:

- OCP only (OCP 7.9 or 8.0) and nanocct only: every test that needs both bindings in one process is skipped - the equivalence of the two kernels on the same mesh (`tests/test_binding_equivalence.py`), objects of two bindings combined or kept apart, mixed scenes, locations of two bindings (`tests/test_kernel.py`), and the comparisons of both bindings' measurements, materials and STEP reading (`tests/test_measure.py`, `tests/test_materials.py`, `tests/test_stepreader.py`).
- Both installed: nothing is skipped. Tests of ocp_tessellate's dispatch run once per installed binding, so this installation runs the most tests.
- OCP 7.9 with build123d 0.12.0 also skips the BuildSheet tests (BuildSheet exists only in later build123d versions).
- `tests/test_cadquery.py` and `tests/test_color.py` import CadQuery: where CadQuery is not installed (as in a nanocct-only environment without a CadQuery port) they cannot be collected and are left out with `--ignore`.
- The emissive factor of materials exists in OCP 7.9 and nanocct but not in OCP 8; `tests/test_materials.py` checks that it reads as None there instead of skipping.

The emissive difference also shows downstream: ocp-viewer-core's two emissive tests skip where the default binding is OCP 8, including an installation of both bindings without `prefer_nanocct(True)`.

## License

Apache 2.0. See [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

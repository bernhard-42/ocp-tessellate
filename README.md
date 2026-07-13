# OCP-Tessellate

Tessellate [OCP](https://github.com/cadquery/OCP) (Python bindings for OpenCascade) shapes into a JSON-friendly format suitable for [three-cad-viewer](https://github.com/bernhard-42/three-cad-viewer) and downstream tooling such as [ocp_vscode](https://github.com/bernhard-42/vscode-ocp-cad-viewer).

It accepts geometry from [CadQuery](https://github.com/CadQuery/cadquery), [build123d](https://github.com/gumyr/build123d), and raw OCP `TopoDS_*` shapes, walks the structure, computes triangulations / discretized edges, and emits a hierarchical group of meshed instances.

## Installation

```bash
pip install ocp-tessellate
```

Requires Python 3.10+ and OCP 7.8 or 7.9.

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
| `BuildPart` / `BuildSketch` / `BuildLine` | a single `OcpObject` for the builder result; `BuildSketch` adds a `sketch_local` sibling unless disabled |

## Compatibility

- Python 3.10+
- OCP 7.8 and 7.9
- build123d (current)
- CadQuery 2.x

## License

Apache 2.0. See [LICENSE](LICENSE).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

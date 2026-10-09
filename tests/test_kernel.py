"""The kernel boundary: ocp_tessellate reaches OCCT only through ocp_tessellate._kernel.

See docs/nanocct-concept.md. The structural tests read the source with ast, so a
module that bypasses the kernel fails here even if the binding it uses happens
to be the one installed. The dispatch tests run once per installed binding.
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from occt_binding import DEFAULT_BINDING, INSTALLED, occt, root

import ocp_tessellate._kernel as kernels
from ocp_tessellate import ImageFace, ocp_utils
from ocp_tessellate._kernel import adapter, binding_of, kernel, kernel_of, kernel_of_all
from ocp_tessellate.convert import tessellate_group, to_ocpgroup

PACKAGE = Path(kernels.__file__).parent.parent
KERNEL_DIR = PACKAGE / "_kernel"
BINDINGS = ("OCP", "nanocct")
# which module may import which binding at runtime: the probes and the kernels
MAY_IMPORT = {
    KERNEL_DIR / "__init__.py": {"OCP", "nanocct"},
    KERNEL_DIR / "ocp_adapter.py": {"OCP"},
    KERNEL_DIR / "nanocct_adapter.py": {"nanocct"},
}
# and only for the type checker: the OCCT types of annotations
MAY_IMPORT_FOR_TYPES = {PACKAGE / "types.py": {"OCP", "nanocct"}}
DEFAULT = root(DEFAULT_BINDING)


#
# Structure
#


def _modules():
    return sorted(PACKAGE.rglob("*.py"))


def _is_type_checking_block(node):
    return isinstance(node, ast.If) and ast.unparse(node.test) in ("TYPE_CHECKING", "typing.TYPE_CHECKING")


def _type_checking_nodes(tree):
    """The ids of all nodes inside `if TYPE_CHECKING:` blocks."""
    ids = set()
    for node in ast.walk(tree):
        if _is_type_checking_block(node):
            for stmt in node.body:
                ids |= {id(n) for n in ast.walk(stmt)}
    return ids


def _imported_bindings(tree, skip_ids):
    found = set()
    for node in ast.walk(tree):
        if id(node) in skip_ids:
            continue
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            found.add(node.module.split(".")[0])
    return found & set(BINDINGS)


def test_only_the_kernels_import_a_binding():
    offenders = {}
    for path in _modules():
        tree = ast.parse(path.read_text())
        type_only = _type_checking_nodes(tree)
        at_runtime = _imported_bindings(tree, type_only)
        for_types = _imported_bindings(tree, set()) - at_runtime
        if not at_runtime <= MAY_IMPORT.get(path, set()):
            offenders[str(path.relative_to(PACKAGE))] = sorted(at_runtime)
        if not for_types <= MAY_IMPORT_FOR_TYPES.get(path, set()) | MAY_IMPORT.get(path, set()):
            offenders[str(path.relative_to(PACKAGE)) + " (TYPE_CHECKING)"] = sorted(for_types)
    assert offenders == {}


def _annotation_ids(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]:
                if arg is not None and arg.annotation is not None:
                    ids |= {id(n) for n in ast.walk(arg.annotation)}
            if node.returns is not None:
                ids |= {id(n) for n in ast.walk(node.returns)}
        elif isinstance(node, ast.AnnAssign):
            ids |= {id(n) for n in ast.walk(node.annotation)}
    return ids


def test_type_checking_names_are_not_used_at_runtime():
    """What a module imports under TYPE_CHECKING (the OCCT types) is only used in
    annotations and in other TYPE_CHECKING code: OCCT objects come from a kernel."""
    offenders = {}
    for path in _modules():
        tree = ast.parse(path.read_text())
        type_only = _type_checking_nodes(tree)
        names = set()
        for node in ast.walk(tree):
            if _is_type_checking_block(node):
                for stmt in node.body:
                    for n in ast.walk(stmt):
                        if isinstance(n, (ast.Import, ast.ImportFrom)):
                            names |= {(a.asname or a.name).split(".")[0] for a in n.names}
                        elif isinstance(n, ast.Assign):
                            names |= {t.id for t in n.targets if isinstance(t, ast.Name)}
                        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                            names.add(n.target.id)
        skip = type_only | _annotation_ids(tree)
        uses = [
            f"{n.id}:{n.lineno}"
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in names and id(n) not in skip
        ]
        if len(uses) > 0:
            offenders[str(path.relative_to(PACKAGE))] = uses
    assert offenders == {}


def _shared_modules():
    return [p for p in _modules() if p.parent != KERNEL_DIR]


def _is_binding_expr(node):
    """`k`, or a call of kernel_of / kernel / binding_of: a binding at runtime."""
    if isinstance(node, ast.Name):
        return node.id == "k"
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("kernel_of", "kernel", "binding_of")
    )


def _occt_paths():
    """Every `<binding>.<package>.<Name>` the shared code reaches."""
    paths = set()
    for path in _shared_modules():
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and _is_binding_expr(node.value.value)
            ):
                paths.add((node.value.attr, node.attr))
    return paths


def _adapter_names():
    """Every `adapter(...).<name>` the shared code uses."""
    names = set()
    for path in _shared_modules():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call):
                func = node.value.func
                if isinstance(func, ast.Name) and func.id == "adapter":
                    names.add(node.attr)
    return names


def _top_level_names(path):
    """Names a module defines at top level, inside version branches (if/else) too."""
    tree = ast.parse(path.read_text())
    defined = set()
    statements = list(tree.body)
    while len(statements) > 0:
        node = statements.pop()
        if isinstance(node, ast.If):
            statements.extend(node.body + node.orelse)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            defined |= {(a.asname or a.name).split(".")[0] for a in node.names}
    return defined


def test_occt_names_follow_the_package_rule():
    """The code writes k.<package>.<Name> with OCCT's package of the name."""
    paths = _occt_paths()
    assert len(paths) > 50
    assert sorted(p for p in paths if p[1].split("_")[0] != p[0]) == []


@pytest.mark.parametrize("binding", INSTALLED)
def test_occt_names_resolve_in_every_binding(binding):
    """Every OCCT class or function the shared code reaches exists in the binding."""
    k = root(binding)
    missing = sorted(
        f"{pkg}.{name}" for pkg, name in _occt_paths() if not hasattr(getattr(k, pkg, None), name)
    )
    assert missing == []


@pytest.mark.parametrize("adapter_file", ["ocp_adapter.py", "nanocct_adapter.py"])
def test_adapters_provide_what_the_code_uses(adapter_file):
    """Both adapters define every difference the code takes from them (statically,
    so in every installation)."""
    used = _adapter_names()
    assert len(used) > 10
    assert sorted(used - _top_level_names(KERNEL_DIR / adapter_file)) == []


#
# Flags and the default kernel
#


def test_flags():
    assert kernels.HAS_OCP is ("OCP" in INSTALLED)
    assert kernels.HAS_NANOCCT is ("nanocct" in INSTALLED)
    assert kernels.KERNELS == tuple(root(b) for b in INSTALLED)
    for b in INSTALLED:
        assert adapter(root(b)).NAME == {"OCP": "ocp", "nanocct": "nanocct"}[b]


def test_default_kernel():
    assert kernel() is DEFAULT


def test_no_occt_names_are_exported():
    for name in ("TopoDS_Shape", "gp_Pnt", "TopLoc_Location", "downcast_LUT"):
        assert not hasattr(ocp_utils, name), name


#
# Dispatch, once per installed binding
#


def _box(binding):
    return occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", binding)(1, 2, 3).Shape()


@pytest.mark.parametrize("binding", INSTALLED)
def test_kernel_of_an_occt_object(binding):
    assert kernel_of(_box(binding)) is root(binding)
    assert kernel_of(occt("gp", "gp_Pnt", binding)(1, 2, 3)) is root(binding)


@pytest.mark.parametrize("binding", INSTALLED)
def test_an_occt_object_keeps_its_binding_whatever_the_default(binding):
    box = _box(binding)
    assert kernel_of(box) is root(binding)
    assert kernel_of_all([box, (1, 2, 3)]) is root(binding)


@pytest.mark.parametrize("binding", INSTALLED)
def test_wrappers_and_sequences(binding):
    """kernel_of takes the OCCT object itself; kernel_of_all a sequence of them."""

    class Wrapper:
        def __init__(self, wrapped):
            self.wrapped = wrapped

    box = _box(binding)
    # wrappers are not looked into (callers pass .wrapped): not an OCCT object
    assert kernel_of(Wrapper(box)) is kernel()
    assert binding_of(Wrapper(box)) is None
    assert not ocp_utils.is_topods_shape(Wrapper(box))
    # a list is not an OCCT object either
    assert kernel_of([box]) is kernel()
    # kernel_of_all: the binding of the OCCT objects, other objects ignored
    assert kernel_of_all([None, 1.0, box]) is root(binding)
    assert kernel_of_all((occt("gp", "gp_Pnt", binding)(), (1, 2, 3))) is root(binding)
    assert kernel_of_all([1.0, (1, 2, 3)]) is kernel()
    assert kernel_of_all([]) is kernel()


@pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
def test_objects_of_two_bindings_do_not_combine():
    with pytest.raises(TypeError, match="objects of two bindings"):
        kernel_of_all([_box("OCP"), _box("nanocct")])
    with pytest.raises(TypeError, match="objects of two bindings"):
        ocp_utils.make_compound([_box("OCP"), _box("nanocct")])


@pytest.mark.parametrize("obj", [None, 1.0, "text", (1.0, 2.0, 3.0), [], object()])
def test_kernel_of_something_else_is_the_default(obj):
    assert kernel_of(obj) is kernel()


@pytest.mark.parametrize("binding", INSTALLED)
def test_kernel_of_does_not_consume_a_generator(binding):
    box = _box(binding)
    gen = (s for s in [box])
    assert kernel_of(gen) is kernel()
    assert list(gen) == [box]


@pytest.mark.parametrize("binding", INSTALLED)
def test_make_compound_of_a_generator_uses_its_binding(binding):
    comp = ocp_utils.make_compound(s for s in [_box(binding), _box(binding)])
    assert kernel_of(comp) is root(binding)
    assert len(list(ocp_utils.get_solids(comp))) == 2


def test_predicates_per_binding():
    for binding in INSTALLED:
        box = _box(binding)
        assert ocp_utils.is_topods_shape(box)
        # Shape() is a TopoDS_Shape; downcast gives the TopoDS_Solid
        assert not ocp_utils.is_topods_solid(box)
        assert ocp_utils.is_topods_solid(ocp_utils.downcast(box))
        assert not ocp_utils.is_topods_face(ocp_utils.downcast(box))
        assert binding_of(box) is root(binding)
    for other in (None, 1.0, "text", (1.0, 2.0, 3.0), object()):
        assert not ocp_utils.is_topods_shape(other)
        assert binding_of(other) is None


@pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
def test_locations_of_two_bindings_do_not_mix():
    """ocp_tessellate creates no locations of its own above the user's objects,
    so a product of locations of two bindings is a bug and raises."""
    outer = ocp_utils.tq_to_loc((1, 2, 3), (0, 0, 0, 1))
    other = "nanocct" if DEFAULT_BINDING == "OCP" else "OCP"
    trsf = occt("gp", "gp_Trsf", other)()
    trsf.SetTranslationPart(occt("gp", "gp_Vec", other)(4, 0, 0))
    inner = occt("TopLoc", "TopLoc_Location", other)(trsf)
    assert binding_of(outer) is root(DEFAULT_BINDING)
    assert binding_of(inner) is root(other)
    with pytest.raises(TypeError, match="locations of two bindings"):
        ocp_utils.mul_locations(outer, inner)


@pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
@pytest.mark.parametrize(
    "scene",
    ["list", "dict", "nested"],
)
def test_mixed_scenes(scene):
    """Lists, dicts and nested containers of OCP and nanocct objects are shown
    together: each object is tessellated with its own binding."""
    def box(binding, x):
        pnt = occt("gp", "gp_Pnt", binding)(x, 0, 0)
        return occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", binding)(pnt, 1, 1, 1).Shape()

    objs = {
        "list": [box("OCP", 0), box("nanocct", 2)],
        "dict": {"a": box("OCP", 0), "b": box("nanocct", 2)},
        "nested": [box("OCP", 0), [box("nanocct", 2), {"c": box("OCP", 4)}]],
    }[scene]
    group, instances = to_ocpgroup(objs)
    meshed, shapes, _ = tessellate_group(group, instances)
    assert len(meshed) == {"list": 2, "dict": 2, "nested": 3}[scene]
    assert shapes["bb"]["xmin"] == pytest.approx(0)
    assert shapes["bb"]["xmax"] == pytest.approx({"list": 3, "dict": 3, "nested": 5}[scene])


#
# Functions that take an OCCT object or plain input: the object decides, the
# default (kernel()) applies to plain input only
#

IMAGE = Path(__file__).with_name("object-160x160mm.png")


def _vec(binding, *xyz):
    return occt("gp", "gp_Vec", binding)(*xyz)


def test_cross_of_tuples():
    x = np.array((1, 2, 3)) / np.linalg.norm((1, 2, 3))
    z = np.array((9, 4, 1)) / np.linalg.norm((9, 4, 1))
    y = np.cross(x, z)
    assert ocp_utils.cross((1, 2, 3), (9, 4, 1)) == pytest.approx(tuple(y / np.linalg.norm(y)))


@pytest.mark.parametrize("binding", INSTALLED)
def test_cross_and_normalized_with_one_occt_vector(binding):
    expected = ocp_utils.cross((1, 0, 0), (0, 0, 1))
    assert ocp_utils.cross(_vec(binding, 1, 0, 0), (0, 0, 1)) == pytest.approx(expected)
    assert ocp_utils.cross((1, 0, 0), _vec(binding, 0, 0, 1)) == pytest.approx(expected)
    assert binding_of(ocp_utils.normalized(_vec(binding, 3, 0, 0))) is root(binding)
    assert binding_of(ocp_utils.normalized((3, 0, 0))) is kernel()


@pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
def test_cross_of_two_bindings_raises():
    with pytest.raises(TypeError, match="objects of two bindings"):
        ocp_utils.cross(_vec("OCP", 1, 0, 0), _vec("nanocct", 0, 0, 1))


@pytest.mark.parametrize("binding", INSTALLED)
def test_line_circle_vertex_rect_take_the_binding_of_any_occt_argument(binding):
    pnt = occt("gp", "gp_Pnt", binding)(1, 0, 0)
    direction = occt("gp", "gp_Dir", binding)(0, 0, 1)
    assert binding_of(ocp_utils.line(pnt, (0, 0, 0))) is root(binding)
    assert binding_of(ocp_utils.line((0, 0, 0), pnt)) is root(binding)
    assert binding_of(ocp_utils.circle(pnt, (0, 0, 1), 1.0)) is root(binding)
    assert binding_of(ocp_utils.circle((0, 0, 0), direction, 1.0)) is root(binding)
    assert binding_of(ocp_utils.vertex(pnt)) is root(binding)
    assert binding_of(ocp_utils.rect(1, 2, occt("gp", "gp_Ax3", binding)())) is root(binding)
    # plain input only: the default
    assert binding_of(ocp_utils.line((0, 0, 0), (1, 0, 0))) is kernel()
    assert binding_of(ocp_utils.vertex((1, 2, 3))) is kernel()
    assert binding_of(ocp_utils.rect(1, 2)) is kernel()


def test_image_face_without_location_uses_the_default():
    face = ImageFace(str(IMAGE))
    assert binding_of(face.objs[0]) is root(DEFAULT_BINDING)
    assert binding_of(face.loc) is root(DEFAULT_BINDING)


@pytest.mark.parametrize("binding", INSTALLED)
def test_image_face_uses_the_binding_of_its_location(binding):
    loc = occt("TopLoc", "TopLoc_Location", binding)()
    face = ImageFace(str(IMAGE), location=loc)
    assert binding_of(face.objs[0]) is root(binding)
    assert binding_of(face.loc) is root(binding)


#
# The three installation cases, simulated by hiding bindings in a subprocess
#

PROBE = """
import json, sys
for name in sys.argv[1:]:
    sys.modules[name] = None  # makes `import <name>` raise ImportError
out = {}
try:
    import ocp_tessellate._kernel as k
except ImportError as e:
    out["error"] = str(e)
else:
    out["flags"] = [k.HAS_OCP, k.HAS_NANOCCT]
    out["default"] = k.kernel().__name__
print(json.dumps(out))
"""


def _probe(hidden, occt_binding=None):
    """Run PROBE in a subprocess with `hidden` bindings and OCCT_BINDING set or unset."""
    env = {k: v for k, v in os.environ.items() if k != "OCCT_BINDING"}
    if occt_binding is not None:
        env["OCCT_BINDING"] = occt_binding
    result = subprocess.run(
        [sys.executable, "-c", PROBE, *hidden], capture_output=True, text=True, check=True, env=env
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("hidden", [(), ("OCP",), ("nanocct",), ("OCP", "nanocct")])
def test_installation_cases(hidden):
    out = _probe(hidden)
    available = [b for b in INSTALLED if b not in hidden]
    if len(available) == 0:
        assert out == {"error": "ocp_tessellate needs OCP (cadquery-ocp) or nanocct"}
        return
    assert out["flags"] == ["OCP" in available, "nanocct" in available]
    assert out["default"] == ("OCP" if "OCP" in available else "nanocct")


@pytest.mark.parametrize("hidden", [(), ("OCP",), ("nanocct",)])
@pytest.mark.parametrize("occt_binding", ["OCP", "nanocct"])
def test_occt_binding_environment_variable(hidden, occt_binding):
    """OCCT_BINDING gives the initial preference; a binding it names must be installed."""
    out = _probe(hidden, occt_binding)
    available = [b for b in INSTALLED if b not in hidden]
    if len(available) == 0:
        assert out == {"error": "ocp_tessellate needs OCP (cadquery-ocp) or nanocct"}
    elif occt_binding not in available:
        assert out == {"error": f"OCCT_BINDING={occt_binding}, but {occt_binding} is not installed"}
    else:
        # "default" is kernel() right after import
        assert out["default"] == occt_binding


def test_occt_binding_must_be_a_binding():
    out = _probe((), "ocp")
    assert out == {"error": "OCCT_BINDING must be one of ('OCP', 'nanocct'), not 'ocp'"}

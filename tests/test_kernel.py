"""The kernel boundary: ocp_tessellate reaches OCCT only through ocp_tessellate._kernel.

See docs/nanocct-concept.md. The structural tests read the source with ast, so a
module that bypasses the kernel fails here even if the binding it uses happens
to be the one installed.
"""

import ast
from pathlib import Path

import pytest
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Pnt
from OCP.TopoDS import TopoDS_Shape

import ocp_tessellate._kernel as kernels
from ocp_tessellate._kernel import ANY, kernel, kernel_of
from ocp_tessellate._kernel import ocp as ocp_kernel

PACKAGE = Path(kernels.__file__).parent.parent
KERNEL_DIR = PACKAGE / "_kernel"
# the probe in _kernel/__init__.py and the kernel module itself
MAY_IMPORT_OCP = {KERNEL_DIR / "__init__.py", KERNEL_DIR / "ocp.py"}


def _modules():
    return sorted(PACKAGE.rglob("*.py"))


def _imports_ocp(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] == "OCP" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if node.module is not None and node.module.split(".")[0] == "OCP":
                return True
    return False


def test_only_the_kernel_imports_ocp():
    offenders = []
    for path in _modules():
        if path in MAY_IMPORT_OCP:
            continue
        if _imports_ocp(ast.parse(path.read_text())):
            offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def _default_names(tree):
    """Names a module imports from the default kernel (for re-export and annotations)."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.endswith("_kernel.default"):
                names |= {a.asname or a.name for a in node.names}
    return names


def _occt_names(path, tree):
    names = _default_names(tree)
    # convert.py takes the ocp_utils names by star import
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.endswith("ocp_utils") and any(a.name == "*" for a in node.names):
                names |= _default_names(ast.parse((PACKAGE / "ocp_utils" / "__init__.py").read_text()))
    return names


def _body_uses(tree, names):
    """Loads of `names` inside function bodies, annotations excluded."""
    uses = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        annotation_ids = set()
        for stmt in fn.body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.AnnAssign):
                    annotation_ids |= {id(n) for n in ast.walk(node.annotation)}
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
                        if arg.annotation is not None:
                            annotation_ids |= {id(n) for n in ast.walk(arg.annotation)}
                    if node.returns is not None:
                        annotation_ids |= {id(n) for n in ast.walk(node.returns)}
        for stmt in fn.body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    if node.id in names and id(node) not in annotation_ids:
                        uses.append(f"{fn.name}:{node.lineno} {node.id}")
    return uses


def test_code_reaches_occt_through_the_kernel():
    """Outside the kernel, OCCT names are used in annotations and re-exports only."""
    offenders = {}
    for path in _modules():
        if path.parent == KERNEL_DIR:
            continue
        tree = ast.parse(path.read_text())
        uses = _body_uses(tree, _occt_names(path, tree))
        if len(uses) > 0:
            offenders[str(path.relative_to(PACKAGE))] = uses
    assert offenders == {}


def test_kernel_all_lists_every_public_name():
    tree = ast.parse((KERNEL_DIR / "ocp.py").read_text())
    defined = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None and node.module.startswith("OCP"):
            defined |= {a.asname or a.name for a in node.names}
    # top-level definitions, including those inside version branches (if/else)
    statements = list(tree.body)
    while len(statements) > 0:
        node = statements.pop()
        if isinstance(node, ast.If):
            statements.extend(node.body + node.orelse)
        elif isinstance(node, ast.FunctionDef):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            defined |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    public = {n for n in defined if not n.startswith("_")} - {"OCP"}
    assert set(ocp_kernel.__all__) == public
    assert all(hasattr(ocp_kernel, n) for n in ocp_kernel.__all__)


def test_flags():
    assert kernels.HAS_OCP is True
    assert kernels.KERNELS == (ocp_kernel,)


def test_kernel_of_an_occt_object():
    box = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
    assert kernel_of(box) is ocp_kernel
    assert kernel_of(gp_Pnt(1, 2, 3)) is ocp_kernel


def test_kernel_of_a_wrapper_and_of_sequences():
    class Wrapper:
        def __init__(self, wrapped):
            self.wrapped = wrapped

    box = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
    assert kernel_of(Wrapper(box)) is ocp_kernel
    assert kernel_of([None, 1.0, box]) is ocp_kernel
    assert kernel_of((gp_Pnt(),)) is ocp_kernel


@pytest.mark.parametrize("obj", [None, 1.0, "text", (1.0, 2.0, 3.0), [], object()])
def test_kernel_of_something_else_is_the_default(obj):
    assert kernel_of(obj) is kernel()


def test_kernel_of_does_not_consume_a_generator():
    box = BRepPrimAPI_MakeBox(1, 2, 3).Shape()
    gen = (s for s in [box])
    assert kernel_of(gen) is kernel()
    assert list(gen) == [box]


def test_any():
    assert ANY.TopoDS_Shape == (TopoDS_Shape,)
    assert isinstance(BRepPrimAPI_MakeBox(1, 2, 3).Shape(), ANY.TopoDS_Shape)
    with pytest.raises(AttributeError):
        ANY.NoSuchClass

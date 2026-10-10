"""StepReader and import_step_as_single_compound, in the run's binding.

The STEP file is written with build123d (in its binding, BINDING) and read
with the default binding: StepReader gets no OCCT object, so it reads with
nanocct where nanocct is installed, else with OCP.
"""

import build123d as bd
import pytest
from occt_binding import DEFAULT_BINDING, build123d_binding, root

from ocp_tessellate._kernel import binding_of
from ocp_tessellate.stepreader import StepReader, import_step_as_single_compound

# the binding build123d writes the STEP file in
BINDING = build123d_binding()


@pytest.fixture(scope="module")
def step_file(tmp_path_factory):
    """An assembly with names, colors, locations, a nested sub assembly."""
    box = bd.Box(1, 2, 3)
    box.label = "box"
    box.color = bd.Color(1, 0, 0)
    ball = bd.Pos(5, 0, 0) * bd.Sphere(1)
    ball.label = "ball"
    ball.color = bd.Color(0, 0, 1)
    cyl = bd.Pos(0, 5, 0) * bd.Cylinder(1, 2)
    cyl.label = "cyl"
    sub = bd.Compound(label="sub", children=[cyl])
    asm = bd.Compound(label="asm", children=[box, ball, sub])
    path = tmp_path_factory.mktemp("step") / "asm.step"
    bd.export_step(asm, str(path))
    return str(path)


def _read(binding, path):
    reader = StepReader()
    reader.load(path)
    return reader


def _translation(loc):
    p = loc.Transformation().TranslationPart()
    return (p.X(), p.Y(), p.Z())


def _summary(objs):
    """name, translation, color and binding of each object, nested as in the file."""
    result = []
    for o in objs:
        shape = o["shape"]
        result.append((
            o["name"],
            None if o["loc"] is None else _translation(o["loc"]),
            o["color"],
            None if shape is None else binding_of(shape).__name__,
            None if o["shapes"] is None else _summary(o["shapes"]),
        ))
    return result


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
def test_names_colors_locations(binding, step_file):
    reader = _read(binding, step_file)
    assert reader.assemblies is not None
    assert len(reader.assemblies) == 1
    (asm,) = reader.assemblies
    assert asm["name"] == "asm"
    names = [o["name"] for o in asm["shapes"]]
    assert names == ["box", "ball", "sub"]
    box, ball, sub = asm["shapes"]
    assert box["color"] == pytest.approx((1, 0, 0, 1))
    assert ball["color"] == pytest.approx((0, 0, 1, 1))
    assert _translation(ball["loc"]) == pytest.approx((5, 0, 0))
    # the nested sub assembly
    assert sub["shape"] is None
    (cyl,) = sub["shapes"]
    assert cyl["name"] == "cyl"
    assert _translation(cyl["loc"]) == pytest.approx((0, 5, 0))
    # the shapes are in the binding the reader read with
    for leaf in (box, ball, cyl):
        assert binding_of(leaf["shape"]) is root(binding)


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
def test_to_build123d(binding, step_file):
    reader = _read(binding, step_file)
    if binding == BINDING:
        assembly = reader.to_build123d()
        assert [c.label for c in assembly.children] == ["box_0", "ball_0", "sub_0"]
        assert binding_of(assembly.wrapped) is root(binding)
    else:
        # build123d wraps the other binding: the reader says what to do
        with pytest.raises(TypeError, match=f"but build123d uses {BINDING}"):
            reader.to_build123d()


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
def test_import_step_as_single_compound(binding, step_file):
    shape = import_step_as_single_compound(step_file)
    assert binding_of(shape) is root(binding)

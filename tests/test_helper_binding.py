"""Helpers ocp_tessellate draws itself take the binding of what they depict.

A coordinate system for a location, an arrow for an axis and the coordinate
systems of a CadQuery assembly's mates are built by ocp_tessellate from plain
coordinates, so no OCCT object decides their binding - and the default,
nanocct where it is installed, is wrong whenever the depicted object is OCP:
a mate's helper sits under the assembly, and the assembly's OCP location
cannot be multiplied with the helper's nanocct one (`mul_locations` raises
"locations of two bindings"). Seen with cadquery-massembly's
`show(assembly, render_mates=True)` where nanocct is installed.
"""

import importlib.util
from types import SimpleNamespace

import pytest
from occt_binding import INSTALLED, occt

from ocp_tessellate._kernel import binding_of
from ocp_tessellate.cad_objects import CoordAxis, CoordSystem
from ocp_tessellate.convert import tessellate_group, to_ocpgroup

HAS_CADQUERY = importlib.util.find_spec("cadquery") is not None


def _bindings(objs):
    return {type(obj).__module__.partition(".")[0] for obj in objs}


def _leaf_shapes(group):
    """Every OCCT shape below an OcpGroup (or of an OcpObject)."""
    objects = getattr(group, "objects", None)
    if objects is not None:
        return [shape for child in objects for shape in _leaf_shapes(child)]
    obj = group.obj
    return list(obj) if isinstance(obj, list) else [obj]


def _identity(binding):
    return occt("TopLoc", "TopLoc_Location", binding)()


@pytest.mark.parametrize("binding", INSTALLED)
def test_a_coordinate_system_takes_the_binding_of_like(binding):
    helper = CoordSystem("cs", (0, 0, 0), (1, 0, 0), (0, 0, 1), like=_identity(binding))
    assert _bindings(helper.objs) == {binding}


@pytest.mark.parametrize("binding", INSTALLED)
def test_an_axis_takes_the_binding_of_like(binding):
    helper = CoordAxis("ax", (0, 0, 0), (0, 0, 1), like=_identity(binding))
    assert _bindings(helper.objs) == {binding}


@pytest.mark.parametrize("binding", INSTALLED)
def test_a_shown_location_is_drawn_in_its_binding(binding):
    group, _ = to_ocpgroup(_identity(binding))
    assert _bindings(_leaf_shapes(group)) == {binding}


@pytest.mark.parametrize("binding", INSTALLED)
def test_a_shown_axis_is_drawn_in_its_binding(binding):
    pnt, direction = occt("gp", "gp_Pnt", binding), occt("gp", "gp_Dir", binding)
    axis = occt("gp", "gp_Ax1", binding)(pnt(0, 0, 0), direction(0, 0, 1))
    group, _ = to_ocpgroup(axis)
    assert _bindings(_leaf_shapes(group)) == {binding}


@pytest.mark.skipif(not HAS_CADQUERY, reason="needs cadquery")
def test_the_mates_of_a_cadquery_assembly_are_drawn_in_its_binding():
    """The failing case: OCP under the assembly, nanocct for the helper.

    cadquery-massembly is not needed: ocp_tessellate reads `mates` from the
    top assembly, a dict of objects with `.mate.origin/x_dir/z_dir` and
    `.assembly`, and that is what this builds.
    """
    import cadquery as cq

    assy = cq.Assembly(name="base", loc=cq.Location((5, 0, 0)))
    assy.add(cq.Workplane().box(1, 1, 1), name="box")
    mate = SimpleNamespace(
        origin=cq.Vector(0, 0, 0), x_dir=cq.Vector(1, 0, 0), z_dir=cq.Vector(0, 0, 1)
    )
    assy.mates = {"m1": SimpleNamespace(mate=mate, assembly=assy)}

    group, instances = to_ocpgroup(assy, render_mates=True)
    tessellate_group(group, instances)

    # a single assembly is the root group itself: base > base_mates, box
    mates = [o for o in group.objects if o.name == "base_mates"]
    assert len(mates) == 1
    cadquery_binding = binding_of(assy.loc.wrapped)
    assert {binding_of(shape) for shape in _leaf_shapes(mates[0])} == {cadquery_binding}

"""to_ocp and to_nanocct: OCCT objects converted between the bindings."""

import math

import pytest
from occt_binding import INSTALLED, occt, root

from ocp_tessellate._kernel import adapter, binding_of
from ocp_tessellate.ocp_utils import downcast, get_faces, to_nanocct, to_ocp
from ocp_tessellate.ocp_utils.serialize import _read, _write_via_file

both = pytest.mark.skipif(len(INSTALLED) < 2, reason="needs OCP and nanocct")
DIRECTIONS = [("OCP", "nanocct"), ("nanocct", "OCP")]
CONVERT = {"OCP": to_ocp, "nanocct": to_nanocct}


def _trsf(b):
    gp = lambda name: occt("gp", name, b)
    trsf = gp("gp_Trsf")()
    trsf.SetRotation(gp("gp_Ax1")(gp("gp_Pnt")(), gp("gp_Dir")(1, 1, 0)), 0.7)
    trsf.SetTranslationPart(gp("gp_Vec")(3, -4, 5))
    return trsf


def _values(trsf):
    return [trsf.Value(row, col) for row in (1, 2, 3) for col in (1, 2, 3, 4)]


def _close(a, b, ulps=4):
    """Equal up to a few ulp: re-normalised directions and matrices move the last bits."""
    return all(math.isclose(x, y, rel_tol=0, abs_tol=ulps * math.ulp(max(abs(x), 1.0))) for x, y in zip(a, b))


@pytest.mark.parametrize("binding", INSTALLED)
def test_an_object_of_the_target_binding_is_returned_as_is(binding):
    pnt = occt("gp", "gp_Pnt", binding)(1, 2, 3)
    assert CONVERT[binding](pnt) is pnt


@pytest.mark.parametrize("binding", INSTALLED)
def test_only_occt_objects(binding):
    with pytest.raises(TypeError, match="not an OCP or nanocct object"):
        CONVERT[binding]((1, 2, 3))


@pytest.mark.skipif(INSTALLED != ["OCP"] and INSTALLED != ["nanocct"], reason="needs one binding only")
def test_the_target_binding_must_be_installed():
    (installed,) = INSTALLED
    other = "nanocct" if installed == "OCP" else "OCP"
    with pytest.raises(ImportError, match=f"{other} is not installed"):
        CONVERT[other](occt("gp", "gp_Pnt", installed)(1, 2, 3))


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_points_vectors_and_coordinates_are_exact(source, target):
    for name in ("gp_Pnt", "gp_Vec", "gp_XYZ"):
        obj = occt("gp", name, source)(0.1, 1 / 3, -2.5)
        result = CONVERT[target](obj)
        assert binding_of(result) is root(target)
        assert type(result).__name__ == name
        assert (result.X(), result.Y(), result.Z()) == (obj.X(), obj.Y(), obj.Z())


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_directions_transformations_and_locations(source, target):
    d = occt("gp", "gp_Dir", source)(1, 1 / 3, 0)
    rd = CONVERT[target](d)
    assert _close((rd.X(), rd.Y(), rd.Z()), (d.X(), d.Y(), d.Z()))

    trsf = _trsf(source)
    assert _close(_values(CONVERT[target](trsf)), _values(trsf))

    loc = occt("TopLoc", "TopLoc_Location", source)(trsf)
    rloc = CONVERT[target](loc)
    assert binding_of(rloc) is root(target)
    assert _close(_values(rloc.Transformation()), _values(trsf))


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_an_identity_location_stays_identity(source, target):
    assert CONVERT[target](occt("TopLoc", "TopLoc_Location", source)()).IsIdentity() is True


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_axes_and_planes(source, target):
    gp = lambda name: occt("gp", name, source)
    p, n, x = gp("gp_Pnt")(1, 2, 3), gp("gp_Dir")(0, 0, 1), gp("gp_Dir")(1, 0, 0)

    def xyz(v):
        return (v.X(), v.Y(), v.Z())

    ax1 = CONVERT[target](gp("gp_Ax1")(p, n))
    assert (xyz(ax1.Location()), xyz(ax1.Direction())) == ((1, 2, 3), (0, 0, 1))
    ax2 = CONVERT[target](gp("gp_Ax2")(p, n, x))
    assert xyz(ax2.YDirection()) == pytest.approx((0, 1, 0))
    left = gp("gp_Ax3")(p, n, x)
    left.YReverse()
    ax3 = CONVERT[target](left)
    assert ax3.Direct() is False
    assert xyz(ax3.YDirection()) == pytest.approx((0, -1, 0))
    pln = CONVERT[target](gp("gp_Pln")(left))
    assert type(pln).__name__ == "gp_Pln"
    assert xyz(pln.Position().YDirection()) == pytest.approx((0, -1, 0))


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_colors(source, target):
    q = lambda name: occt("Quantity", name, source)
    linear = q("Quantity_TypeOfColor").Quantity_TOC_RGB
    color = q("Quantity_Color")(0.25, 0.5, 0.125, linear)
    rc = CONVERT[target](color)
    assert (rc.Red(), rc.Green(), rc.Blue()) == (0.25, 0.5, 0.125)
    rgba = CONVERT[target](q("Quantity_ColorRGBA")(color, 0.75))
    assert binding_of(rgba) is root(target)
    assert rgba.Alpha() == pytest.approx(0.75)
    assert (rgba.GetRGB().Red(), rgba.GetRGB().Green(), rgba.GetRGB().Blue()) == (0.25, 0.5, 0.125)


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_shapes_with_location_orientation_and_triangulation(source, target):
    trsf = _trsf(source)
    box = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", source)(1, 2, 3).Solid()
    # Moved and Reversed return a TopoDS_Shape: downcast to test that the solid stays one
    box = downcast(box.Moved(occt("TopLoc", "TopLoc_Location", source)(trsf)).Reversed())
    occt("BRepMesh", "BRepMesh_IncrementalMesh", source)(box, 0.1)

    result = CONVERT[target](box)
    assert binding_of(result) is root(target)
    assert type(result).__name__ == "TopoDS_Solid"
    assert result.Orientation().name == "TopAbs_REVERSED"
    assert _close(_values(result.Location().Transformation()), _values(trsf))

    def nodes(shape, b):
        loc = occt("TopLoc", "TopLoc_Location", b)()
        out = []
        for face in get_faces(shape):
            tri = occt("BRep", "BRep_Tool", b).Triangulation_s(face, loc)
            out.append([(p.X(), p.Y(), p.Z()) for p in (tri.Node(i) for i in range(1, tri.NbNodes() + 1))])
        return out

    # the mesh travels with the shape: the same nodes, no re-meshing
    assert nodes(result, target) == nodes(box, source)


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_a_generic_shape_stays_generic(source, target):
    shape = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", source)(1, 1, 1).Shape()
    assert type(CONVERT[target](shape)).__name__ == type(shape).__name__


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_shapes_use_the_common_format_version(source, target):
    common = min(adapter(root(source)).bin_format_upper, adapter(root(target)).bin_format_upper)
    shape = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", source)(1, 1, 1).Shape()
    # every version up to the common one is written by the source and read by the target
    for version in range(1, common + 1):
        buffer = adapter(root(source)).bin_write(shape, True, True, version)
        assert len(list(get_faces(_read(root(target), buffer)))) == 6


@both
@pytest.mark.parametrize(("source", "target"), DIRECTIONS)
def test_other_types_are_refused(source, target):
    line = occt("Geom", "Geom_Line", source)(occt("gp", "gp_Ax1", source)())
    with pytest.raises(TypeError, match=f"cannot convert {source}.Geom_Line to {target}"):
        CONVERT[target](line)


@pytest.mark.parametrize("binding", INSTALLED)
@pytest.mark.parametrize("triangles", [True, False])
def test_serialize_file_fallback_keeps_the_triangulation(binding, triangles):
    """serialize's fallback (a temporary file) writes the triangulation as asked."""
    box = occt("BRepPrimAPI", "BRepPrimAPI_MakeBox", binding)(1, 2, 3).Shape()
    occt("BRepMesh", "BRepMesh_IncrementalMesh", binding)(box, 0.1)
    k = root(binding)
    in_memory = adapter(k).bin_write(box, triangles, False)
    via_file = _write_via_file(k, box, triangles, False)
    assert via_file == in_memory
    loc = occt("TopLoc", "TopLoc_Location", binding)()
    tris = [occt("BRep", "BRep_Tool", binding).Triangulation_s(f, loc) for f in get_faces(_read(k, via_file))]
    assert all(t is not None for t in tris) is triangles

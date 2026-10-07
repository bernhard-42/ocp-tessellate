"""vis_material_values and make_vis_material, once per installed binding."""

import importlib

import pytest
from occt_binding import DEFAULT_BINDING, INSTALLED, occt, root

from ocp_tessellate._kernel import binding_of
from ocp_tessellate.ocp_utils import ALPHA_MODES, make_vis_material, vis_material_values


def _has_emissive(binding):
    """OCP 7.9 and nanocct bind XCAFDoc_VisMaterialPBR.EmissiveFactor, OCP 8 does not."""
    if binding == "nanocct":
        return True
    return hasattr(importlib.import_module("OCP.gp"), "gp_Vec3f")


def _make(binding, *args, **kwargs):
    """make_vis_material gets no OCCT object: it builds in the run's binding."""
    vis = make_vis_material(*args, **kwargs)
    assert binding_of(vis) is root(binding)
    return vis


@pytest.mark.parametrize("binding", INSTALLED)
def test_an_empty_material_has_no_values(binding):
    assert vis_material_values(occt("XCAFDoc", "XCAFDoc_VisMaterial", binding)()) is None


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
def test_round_trip(binding):
    vis = _make(
        binding,
        "Copper",
        color=(0.9, 0.5, 0.3),
        alpha=0.5,
        metallic=0.7,
        roughness=0.2,
        ior=1.4,
        alpha_mode="Mask",
        alpha_cutoff=0.3,
        double_sided=True,
    )
    values = vis_material_values(vis)
    assert values is not None
    assert values["name"] == "Copper"
    assert values["color"] == pytest.approx((0.9, 0.5, 0.3), abs=1e-6)
    assert values["alpha"] == pytest.approx(0.5)
    assert values["metallic"] == pytest.approx(0.7)
    assert values["roughness"] == pytest.approx(0.2)
    assert values["ior"] == pytest.approx(1.4)
    assert values["alpha_mode"] == "Mask"
    assert values["alpha_cutoff"] == pytest.approx(0.3)
    assert values["double_sided"] is True


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
def test_defaults(binding):
    values = vis_material_values(_make(binding, "plain"))
    assert values is not None
    # OCCT's defaults: alpha mode BlendAuto with cutoff 0.5, single-sided
    assert values["alpha_mode"] == "BlendAuto"
    assert values["alpha_cutoff"] == pytest.approx(0.5)
    assert values["double_sided"] is False
    assert values["alpha"] == pytest.approx(1.0)
    # without a color the default base color keeps, with alpha applied
    default_color = vis_material_values(_make(binding, "plain"))["color"]
    translucent = vis_material_values(_make(binding, "translucent", alpha=0.25))
    assert translucent["color"] == pytest.approx(default_color)
    assert translucent["alpha"] == pytest.approx(0.25)


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
@pytest.mark.parametrize("mode", ALPHA_MODES)
def test_alpha_modes(binding, mode):
    assert vis_material_values(_make(binding, "m", alpha_mode=mode))["alpha_mode"] == mode


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
def test_invalid_alpha_settings(binding):
    with pytest.raises(ValueError, match="alpha_mode must be one of"):
        _make(binding, "m", alpha_mode="mask")
    with pytest.raises(ValueError, match="needs an alpha_mode"):
        _make(binding, "m", alpha_cutoff=0.4)


@pytest.mark.parametrize("binding", [DEFAULT_BINDING])
def test_emissive(binding):
    values = vis_material_values(_make(binding, "glow", emissive=(0.5, 0.25, 0.1)))
    if _has_emissive(binding):
        assert values["emissive"] == pytest.approx((0.5, 0.25, 0.1))
        assert vis_material_values(_make(binding, "dark"))["emissive"] == (0.0, 0.0, 0.0)
    else:
        assert values["emissive"] is None


@pytest.mark.parametrize("binding", INSTALLED)
def test_unnamed_and_common_materials(binding):
    common = occt("XCAFDoc", "XCAFDoc_VisMaterialCommon", binding)()
    quantity = importlib.import_module(f"{binding}.Quantity")
    common.DiffuseColor = quantity.Quantity_Color(0.2, 0.4, 0.6, quantity.Quantity_TypeOfColor.Quantity_TOC_RGB)
    common.IsDefined = True
    vis = occt("XCAFDoc", "XCAFDoc_VisMaterial", binding)()
    vis.SetCommonMaterial(common)
    values = vis_material_values(vis)
    assert values is not None
    assert values["name"] is None
    # read through ConvertToPbrMaterial: linear 0.2, 0.4, 0.6 as sRGB
    assert values["color"] == pytest.approx((0.4845, 0.6652, 0.7977), abs=1e-4)
    assert vis.HasPbrMaterial() is False

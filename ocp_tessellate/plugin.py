"""What a kernel plugin builds on: an object of a kernel other than OCCT goes through the
regular pipeline (https://bernhard-42.github.io/ocp_viewer_docs/plugins/overview/).

A plugin implements `TessellationProtocol` and `ShowProtocol`, hands them to `register_show`
in a module of its own, and declares that module as an entry point of the group
`ocp_viewer.kernels.show`, keyed by its kernel tag, so the host's `show` and `show_all` take the
kernel's objects like any other. It does the same for `BackendProtocol` of ocp_viewer_core,
with `register_plugin` and the group `ocp_viewer.kernels.backend`. Its `convert` makes an `OcpObject` holding the
kernel's shape, and a `CoordSystem` or `CoordAxis` with `like=obj` for a location, plane
or axis. `SURFACE_TYPES` and `CURVE_TYPES` are the type codes of a Tessellation by name.
"""

from __future__ import annotations

from ocp_tessellate._show_registry import register_show
from ocp_tessellate.cad_objects import CoordAxis, CoordSystem, OcpObject
from ocp_tessellate.ocp_utils.location import Placement
from ocp_tessellate.protocols import (
    CURVE_TYPES,
    SURFACE_TYPES,
    ShowProtocol,
    TessellationProtocol,
)
from ocp_tessellate.tessellator import validate_tessellation
from ocp_tessellate.utils import Color

__all__ = [
    "CURVE_TYPES",
    "SURFACE_TYPES",
    "CoordAxis",
    "CoordSystem",
    "OcpObject",
    "Placement",
    "ShowProtocol",
    "TessellationProtocol",
    "object_color",
    "register_show",
    "validate_tessellation",
]



def object_color(obj, color=None, alpha=None) -> Color | None:
    """A given color, else the object's own `color` attribute, else None, for which the
    pipeline fills in the host's default of the kind."""
    own = getattr(obj, "color", None)
    if color is not None:
        c = Color(color)
    elif own is not None:
        c = Color(own)
    else:
        return None
    if alpha is not None:
        c.a = alpha
    return c

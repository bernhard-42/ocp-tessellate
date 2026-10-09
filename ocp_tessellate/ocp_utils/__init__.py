#
# Copyright 2023 Bernhard Walter
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


"""OCCT helpers, grouped by topic in the submodules and re-exported here.

The helpers work on OCP and nanocct objects alike (see ocp_tessellate._kernel).
OCCT classes themselves are not exported: import them from the binding."""

from __future__ import annotations

# ruff: noqa: F401
from ..types import (
    Build123dBuilder,
    Build123dGroupBy,
    Build123dLineBuilder,
    Build123dLocationList,
    Build123dPartBuilder,
    Build123dShape,
    Build123dShapeList,
    Build123dSheetBuilder,
    Build123dSketchBuilder,
    Build123dVector,
    CadqueryAssembly,
    CadquerySketch,
    CadqueryWorkplane,
    Wrapped,
)
from ..utils import Color, distance, type_name
from .bbox import (
    BoundingBox,
    NumpyBBox,
    bounding_box,
    cache,
    get_size,
    make_key,
    nested_bounding_box,
    np_bbox,
)
from .bindings import to_nanocct, to_ocp
from .color import get_rgba, is_ocp_color, ocp_color
from .compat import (
    occt_version,
)
from .detect import (
    is_build123d,
    is_build123d_assembly,
    is_build123d_axis,
    is_build123d_compound,
    is_build123d_groupby,
    is_build123d_line,
    is_build123d_location,
    is_build123d_locationlist,
    is_build123d_part,
    is_build123d_plane,
    is_build123d_shape,
    is_build123d_shapelist,
    is_build123d_sheet,
    is_build123d_shell,
    is_build123d_sketch,
    is_cadquery,
    is_cadquery_assembly,
    is_cadquery_empty_workplane,
    is_cadquery_massembly,
    is_cadquery_shape,
    is_cadquery_sketch,
    is_massembly,
    is_vector,
)
from .geometry import (
    angle_between,
    axis,
    axis_to_line,
    circle,
    cross,
    face_center_location,
    get_plane,
    get_point,
    get_tuple,
    is_plane_xy,
    is_same_plane,
    line,
    normalized,
    point,
    rect,
    tangent_edge_at,
    trim_infinite_edge,
    trim_infinite_face,
    vector,
    vertex,
)
from .location import (
    AxisCoord,
    LocationCoord,
    VectorLike,
    axis_to_vecs,
    copy_location,
    get_axis_coord,
    get_location,
    get_location_coord,
    identity_location,
    is_identity,
    loc_from_gp_pln,
    loc_to_tq,
    loc_to_vecs,
    mul_locations,
    relocate,
    rotate,
    tq_to_loc,
)
from .materials import (
    ALPHA_MODES,
    VisMaterialValues,
    make_vis_material,
    vis_material_values,
)
from .measure import (
    area,
    center_of_geometry,
    center_of_mass,
    closest_directions,
    dist_shapes,
    end_points,
    face_normal,
    length,
    position_at,
    tangent_at,
    volume,
)
from .predicates import (
    is_closed,
    is_compound,
    is_compsolid,
    is_degenerated_edge,
    is_degenerated_face,
    is_edge,
    is_empty_compound,
    is_face,
    is_forward,
    is_gp_axis,
    is_gp_plane,
    is_gp_vec,
    is_line,
    is_location,
    is_shape,
    is_shell,
    is_solid,
    is_toploc_location,
    is_topods_compound,
    is_topods_compsolid,
    is_topods_edge,
    is_topods_face,
    is_topods_shape,
    is_topods_shell,
    is_topods_solid,
    is_topods_vertex,
    is_topods_wire,
    is_vertex,
    is_wire,
    is_wrapped,
)
from .serialize import deserialize, ocp_hash, serialize
from .topology import (
    copy_shape,
    copy_topods_shape,
    downcast,
    extent_or_size,
    get_compound_type,
    get_compounds,
    get_curve,
    get_downcasted_shape,
    get_edge_type,
    get_edges,
    get_face_type,
    get_faces,
    get_solids,
    get_surface,
    get_tshape,
    get_vertices,
    get_wires,
    is_mixed_compound,
    list_topods_compound,
    make_compound,
    make_compsolid,
    unroll_compound,
    unroll_topods_compound,
)

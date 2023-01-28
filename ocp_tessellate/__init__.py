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

import warnings

from ._version import __version__ as ot_version
from ._version import __version_info__ as ot_version_info
from .cad_objects import OCP_Edges, OCP_Faces, OCP_Part, OCP_PartGroup, OCP_Vertices
from .convert import web_color
from .defaults import (
    create_args,
    get_default,
    get_defaults,
    reset_defaults,
    set_defaults,
)
from .ocp_utils import is_cadquery, occt_version
from .serialize import deserialize, serialize
from .utils import Color, warn


def versions():
    print("ocp_tessellate ", ot_version)
    print("open cascade   ", occt_version())


class Part(OCP_Part):
    def __init__(
        self, shape, name="Part", color=None, show_faces=True, show_edges=True
    ):
        if is_cadquery(shape):
            super().__init__(
                [o.wrapped for o in shape.objects],
                name=name,
                color=color,
                show_faces=show_faces,
                show_edges=show_edges,
            )
        elif hasattr(shape, "wrapped"):
            super().__init__(
                shape.wrapped,
                name=name,
                color=color,
                show_faces=show_faces,
                show_edges=show_edges,
            )
        else:
            raise TypeError(f"Type {type(shape)} not support by Part")


class Faces(OCP_Faces):
    def __init__(
        self, faces, name="Faces", color=None, show_faces=True, show_edges=True
    ):
        super().__init__(
            [face.wrapped for face in faces.objects],
            name=name,
            color=color,
            show_faces=show_faces,
            show_edges=show_edges,
        )


class Edges(OCP_Edges):
    def __init__(self, edges, name="Edges", color=None, width=1):
        super().__init__(
            [edge.wrapped for edge in edges.objects],
            name=name,
            color=color,
            width=width,
        )


class Vertices(OCP_Vertices):
    def __init__(self, vertices, name="Vertices", color=None, size=1):
        super().__init__(
            [vertex.wrapped for vertex in vertices.objects], name=name, size=size
        )


class PartGroup(OCP_PartGroup):
    def __init__(self, objects, name="Group", loc=None):
        if loc is not None:
            loc = loc.wrapped
        super().__init__(objects, name=name, loc=loc)

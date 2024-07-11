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
from .cad_objects import (
    ImageFace,
    OCP_Edges,
    OCP_Faces,
    OCP_Part,
    OCP_PartGroup,
    OCP_Vertices,
    OcpGroup,
    OcpObject,
)

# from .convert import web_color
from .defaults import (
    create_args,
    get_default,
    get_defaults,
    reset_defaults,
    set_defaults,
)
from .ocp_utils import is_cadquery, occt_version
from .utils import Color, warn


def versions():
    print("ocp_tessellate ", ot_version)
    print("open cascade   ", occt_version())

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


"""OCP version differences in one place: the TopoDS downcasts, the TopTools
map classes, the hash of a shape, and the OCCT version."""

import OCP
from OCP.TopoDS import TopoDS
if OCP.__version__.startswith("7"):
    from OCP.TopTools import (
        TopTools_IndexedDataMapOfShapeListOfShape,
        TopTools_IndexedMapOfShape,
    )
else:
    from OCP.collections import (
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedDataMapOfShapeListOfShape,
        IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape,
    )


_Vertex = TopoDS.Vertex if hasattr(TopoDS, "Vertex") else TopoDS.Vertex_s
_Edge = TopoDS.Edge if hasattr(TopoDS, "Edge") else TopoDS.Edge_s
_Wire = TopoDS.Wire if hasattr(TopoDS, "Wire") else TopoDS.Wire_s
_Face = TopoDS.Face if hasattr(TopoDS, "Face") else TopoDS.Face_s
_Shell = TopoDS.Shell if hasattr(TopoDS, "Shell") else TopoDS.Shell_s
_Solid = TopoDS.Solid if hasattr(TopoDS, "Solid") else TopoDS.Solid_s
_CompSolid = TopoDS.CompSolid if hasattr(TopoDS, "CompSolid") else TopoDS.CompSolid_s
_Compound = TopoDS.Compound if hasattr(TopoDS, "Compound") else TopoDS.Compound_s


def occt_version() -> str:
    return OCP.__version__


if OCP.__version__.startswith("7.7"):

    def hash_compat(obj):
        MAX_HASH_KEY = 2147483647
        return obj.HashCode(MAX_HASH_KEY)

else:
    hash_compat = hash

import os
import time
import unicodedata
from copy import copy as shallow_copy
from typing import Union

from typing_extensions import TypedDict

try:
    import cadquery as cq  # pyright: ignore[reportMissingImports]  # ty:ignore[unresolved-import]
except ImportError:
    pass

try:
    from build123d import *

    def clone(obj, label=None, color=None, location=None):
        new_obj = shallow_copy(obj)
        if label is not None:
            new_obj.label = label
        if color is not None:
            new_obj.color = color
        if location is None:
            return new_obj
        else:
            return new_obj.move(location)

except ImportError:
    pass

import OCP  # noqa: F401
from OCP.IFSelect import IFSelect_RetDone
from OCP.Quantity import Quantity_ColorRGBA
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_ChildIterator, TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFDoc import (
    XCAFDoc_ColorCurv,
    XCAFDoc_ColorGen,
    XCAFDoc_ColorSurf,
    XCAFDoc_ColorTool,
    XCAFDoc_DocumentTool,
    XCAFDoc_ShapeTool,
)

# from ocp_tessellate.ocp_utils import deserialize, loc_to_tq, serialize, tq_to_loc
from ocp_tessellate.utils import warn
from ocp_tessellate.ocp_utils import make_compound

DEFAULT_COLOR = (0.8, 0.8, 0.8, 1)

RGBA = tuple[float, float, float, float]


class AssemblyObject(TypedDict):
    name: str
    loc: Union[TopLoc_Location, None]
    color: Union[RGBA, None]
    shape: Union[TopoDS_Shape, None]
    shapes: Union["list[AssemblyObject]", None]


def clean_string(s):
    return (
        ""
        .join(ch for ch in s if unicodedata.category(ch)[0] != "C")
        .replace(" ", "_")
        .replace(".", "_")
        .replace("(", "_")
        .replace(")", "_")
    )


class StepReader:
    def __init__(self, analyse_faces=True, split_compounds=True, use_colors=True):
        self.analyse_faces = analyse_faces
        self.split_compounds = split_compounds
        self.use_colors = use_colors
        self.shape_tool: Union[XCAFDoc_ShapeTool, None] = None
        self.color_tool: Union[XCAFDoc_ColorTool, None] = None
        self.assemblies: Union[list[AssemblyObject], None] = None

    def _create_assembly_object(
        self,
        name: str,
        loc: Union[TopLoc_Location, None] = None,
        color: Union[RGBA, None] = None,
        shape: Union[TopoDS_Shape, None] = None,
        children: Union["list[AssemblyObject]", None] = None,
    ) -> AssemblyObject:
        """
        Create a new object
        :param name: object name
        :param loc: object location (TopLoc_Location)
        :param color: 4 tuple (RGBA) with values 0<=x<=1
        :param shape: object shape (TopoDS_Shape)
        :param children: list of AssemblyObject objects
        :return: AssemblyObject
        """
        return {
            "name": name,
            "loc": loc,
            "color": color,
            "shape": shape,
            "shapes": children,
        }

    def get_name(self, label):
        """
        Get name of a TDF_Label object
        :param label: TDF_label of a STEP file
        :return: str
        """
        t = TDataStd_Name()
        if label.FindAttribute(TDataStd_Name.GetID_s(), t):
            name = TCollection_AsciiString(t.Get()).ToCString()
            return clean_string(name)
        else:
            return "Component"

    def get_color(self, shape):
        """
        Get color of a TDF_Label object:
        - if self.use_color is False, return DEFAULT_COLOR, else analyse colors
        - if self.analyse_faces, get all colors of all faces. if all faces have the same color, return it, else return the shape color
        Note: This is BEST EFFORT only. Jupyter-CadQuery does not support different colors for the faces of a solid/compound.
              So for many STEP files with colored faces, the result will not be correct and depend on the structure of the STEP labels
        :param label: TDF_label or TopoDS_Shape of a STEP file
        :return: str
        """

        def to_list(c: Quantity_ColorRGBA) -> RGBA:
            return (c.GetRGB().Red(), c.GetRGB().Green(), c.GetRGB().Blue(), c.Alpha())

        def get_col(obj) -> Union[RGBA, None]:
            color_tool = self.color_tool
            assert color_tool is not None, "load() first"
            col = Quantity_ColorRGBA()
            if (
                color_tool.GetColor(obj, XCAFDoc_ColorGen, col)
                or color_tool.GetColor(obj, XCAFDoc_ColorSurf, col)
                or color_tool.GetColor(obj, XCAFDoc_ColorCurv, col)
            ):
                return to_list(col)
            return None

        if not self.use_colors:
            return DEFAULT_COLOR

        shape_color = get_col(shape)

        colors = []
        if self.analyse_faces:
            # Find all face colors
            exp = TopExp_Explorer(shape, TopAbs_FACE)
            while exp.More():
                color = get_col(exp.Current())
                if color is not None:
                    colors.append(color)
                exp.Next()

            colors = list(set(colors))

        # If all faces have the same color, use this as shape color
        if len(colors) == 1:
            return colors[0]
        else:
            return DEFAULT_COLOR if shape_color is None else shape_color

    def get_location(self, label):
        """
        Get location of a TDF_Label object
        :param label: TDF_label of a STEP file
        :return: TopLoc_Location
        """
        assert self.shape_tool is not None, "load() first"
        return self.shape_tool.GetLocation_s(label)

    def get_shape(self, label):
        """
        Get shape of a TDF_Label object
        :param label: TDF_label of a STEP file
        :return: TopoDS_Shape
        """
        assert self.shape_tool is not None, "load() first"
        return self.shape_tool.GetShape_s(label)

    def get_shape_details(self, label, name, loc):
        """
        Get shape details of a TopAbs_COMPOUND or TopAbs_COMPSOLID
        :param label: TDF_label of a STEP file
        :param name: object name
        :param loc: object location (TopLoc_Location)
        :return: list of TopAbs_SOLID
        """
        it = TDF_ChildIterator()
        it.Initialize(label)
        i = 0
        shapes = []
        while it.More():
            shape = self.get_shape(it.Value())
            if shape.ShapeType() == TopAbs_SOLID:
                s_name = f"{name}_{i + 1}"
                color = self.get_color(shape)
                sub_shape = self._create_assembly_object(s_name, loc, color, shape)
                shapes.append(sub_shape)
                i += 1

            elif shape.ShapeType() == TopAbs_COMPSOLID:
                warn(f"Nested compsolids not supported yet: {name}")

            it.Next()

        return shapes

    def get_subshapes(self, label=None, loc=None):
        """
        Get sub shapes of STEP assemblies
        :param label: TDF_label of a STEP file
        :param loc: object location (TopLoc_Location)
        :return: list of AssemblyObjects
        """
        shape_tool = self.shape_tool
        assert shape_tool is not None, "load() first"
        labels = TDF_LabelSequence()
        if label is None:
            # Get all non referenced top level labels
            shape_tool.GetFreeShapes(labels)
        else:
            # get all sub-components of the label
            shape_tool.GetComponents_s(label, labels)

        result: list[AssemblyObject] = []

        for i in range(labels.Length()):
            sub_label = labels.Value(i + 1)

            if shape_tool.IsReference_s(sub_label):
                ref_label = TDF_Label()
                shape_tool.GetReferredShape_s(sub_label, ref_label)
            else:
                ref_label = sub_label

            is_assembly = shape_tool.IsAssembly_s(ref_label)

            # Get location from the sub_label and everything else from the referenced label
            loc = self.get_location(sub_label)
            name = self.get_name(ref_label)
            shape = self.get_shape(ref_label)

            sub_shape = self._create_assembly_object(name, loc)

            if is_assembly:
                sub_shape["shapes"] = self.get_subshapes(ref_label)

            elif (
                self.split_compounds
                and shape.ShapeType() in [TopAbs_COMPOUND, TopAbs_COMPSOLID]
                and ref_label.HasChild()
            ):
                sub_shapes = self.get_shape_details(ref_label, name, TopLoc_Location())
                if len(sub_shapes) == 0:
                    sub_shape["shape"] = shape
                    sub_shape["color"] = self.get_color(shape)
                else:
                    sub_shape["shapes"] = sub_shapes

            else:
                sub_shape["shape"] = shape
                sub_shape["color"] = self.get_color(shape)

            result.append(sub_shape)

        return result

    def load_assembly(self, cache_filename: str) -> None:
        raise NotImplementedError(
            "The binary assembly cache was removed, load without cache_name"
        )

    def save_assembly(self, cache_filename: str) -> None:
        raise NotImplementedError(
            "The binary assembly cache was removed, load without cache_name"
        )

    def load(self, filename, cache_name=None, clear_cache=False):
        """
        Load a STEP file
        The result will be stores as a list of AssemblyObjects in self.assemblies and
        for faster reload saved in a pickle format with binary BRep buffers
        :param filename: name of the STEP file
        :param cache_name: name of the binary cache object
        :param clear_cache: clear cache before loading to force analysis of STEP file
        """
        start = time.time()
        if cache_name is not None:
            cache_filename = f"{cache_name}.jq"
            if os.path.exists(cache_filename):
                if clear_cache:
                    os.unlink(cache_filename)
                    print("Cache cleared")
                else:
                    print("Loading from cache ... ", flush=True, end="")
                    self.load_assembly(cache_filename)
                    print("done")
                    print(f"duration: {time.time() - start:5.1f} s")
                    return

        if not os.path.exists(filename):
            raise FileNotFoundError(filename)

        print("Reading STEP file ... ", flush=True, end="")
        time.sleep(0.01)  # ensure output is shown

        fmt = TCollection_ExtendedString("CadQuery-XCAF")
        doc = TDocStd_Document(fmt)

        self.shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        self.color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        reader.SetColorMode(True)
        reader.SetLayerMode(True)

        reader.ReadFile(filename)
        reader.Transfer(doc)

        print("parsing Assembly ... ", flush=True, end="")

        self.assemblies = self.get_subshapes()

        print("done")
        print(f"duration: {time.time() - start:5.1f} s")

        if cache_name is not None:
            print("Saving to cache ... ", flush=True, end="")
            self.save_assembly(cache_filename)
            print("done")

    def to_cadquery(self, path=None):
        """
        Convert internal AssemblyObjects format to CadQuery Assemblies
        :return: cadquery.Assembly
        """

        def to_workplane(obj):
            return cq.Workplane(obj=cq.Solid(obj))

        def to_loc(loc: Union[TopLoc_Location, None]) -> "cq.Location":
            return cq.Location() if loc is None else cq.Location(loc)

        def walk(objs: "list[AssemblyObject]", name=None, loc=None):
            a = cq.Assembly(name=name, loc=loc)
            names = {}
            for obj in objs:
                name = obj["name"]

                # Create a unique name by postfixing the enumerator index if needed
                if names.get(name) is None:
                    names[name] = 0
                else:
                    names[name] += 1
                name = f"{obj['name']}_{names[name]}"

                a.add(
                    (
                        to_workplane(obj["shape"])
                        if obj["shapes"] is None
                        else walk(obj["shapes"])
                    ),
                    name=name,
                    color=None if obj["color"] is None else cq.Color(*obj["color"]),
                    loc=to_loc(obj.get("loc")),
                )

            return a

        assemblies = self.assemblies
        assert assemblies is not None, "load() first"

        first = assemblies[0]["shapes"]
        if len(assemblies) == 0 or (first is not None and len(first) == 0):
            raise ValueError("Empty assembly list")

        if len(assemblies) == 1:
            assembly = assemblies[0]
            if assembly["shapes"] is not None:
                return walk(
                    assembly["shapes"], assembly["name"], to_loc(assembly["loc"])
                )
            elif assembly["shape"] is not None:
                return walk([assembly], assembly["name"], to_loc(assembly["loc"]))
            else:
                raise ValueError("No shapes in the first asssembly")
        else:
            result = cq.Assembly(name="Group")
            for assembly in assemblies:
                shapes = assembly["shapes"]
                assert shapes is not None, "top level assembly without shapes"
                result.add(walk(shapes, assembly["name"], to_loc(assembly["loc"])))

        if path is not None:
            result = result.objects[path].obj

        return result

    def to_build123d(self):
        """
        Convert internal AssemblyObjects format to build123d Assemblies
        :return: buiild123d assembly
        """

        def to_loc(loc: Union[TopLoc_Location, None]) -> "Location":
            return Location() if loc is None else Location(loc)

        def walk(objs: "list[AssemblyObject]", label=None, loc=None):
            a = []
            names = {}
            for obj in objs:
                label = obj["name"]

                # Create a unique name by postfixing the enumerator index if needed
                if names.get(label) is None:
                    names[label] = 0
                else:
                    names[label] += 1
                label = f"{obj['name']}_{names[label]}"

                if obj["shapes"] is None:
                    shape = obj["shape"]
                    assert shape is not None, "leaf without shape"
                    # build123d annotates Compound with TopoDS_Compound only,
                    # but it accepts any TopoDS_Shape at runtime
                    child = Compound(shape)  # ty: ignore[invalid-argument-type]
                else:
                    child = walk(obj["shapes"])
                a.append(
                    clone(
                        child,
                        label=label,
                        color=None if obj["color"] is None else Color(*obj["color"]),
                        location=to_loc(obj.get("loc")),
                    )
                )
            result = Compound(label="" if label is None else label, children=a)
            if loc is not None:
                result.location = loc
            return result

        assemblies = self.assemblies
        assert assemblies is not None, "load() first"

        first = assemblies[0]["shapes"]
        if len(assemblies) == 0 or (first is not None and len(first) == 0):
            raise ValueError("Empty assembly list")

        if len(assemblies) == 1:
            assembly = assemblies[0]
            shapes = assembly["shapes"]
            assert shapes is not None, "top level assembly without shapes"
            return walk(shapes, assembly["name"], to_loc(assembly["loc"]))
        else:
            children = []
            for assembly in assemblies:
                shapes = assembly["shapes"]
                assert shapes is not None, "top level assembly without shapes"
                children.append(walk(shapes, assembly["name"], to_loc(assembly["loc"])))
            result = Compound(label="Group", children=children)

        return result


def import_step_as_single_compound(file_name):
    reader = STEPControl_Reader()
    read_status = reader.ReadFile(file_name)
    if read_status != IFSelect_RetDone:
        raise ValueError(f"STEP File {file_name} could not be loaded")
    for i in range(reader.NbRootsForTransfer()):
        reader.TransferRoot(i + 1)

    occ_shapes = []
    for i in range(reader.NbShapes()):
        occ_shapes.append(reader.Shape(i + 1))

    if len(occ_shapes) == 1:
        return occ_shapes[0]
    else:
        return make_compound(occ_shapes)

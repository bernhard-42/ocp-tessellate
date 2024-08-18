import base64
import math

import imagesize

from ocp_tessellate.defaults import get_default
from ocp_tessellate.ocp_utils import (
    axis_to_vecs,
    copy_location,
    copy_topods_shape,
    identity_location,
    line,
    loc_to_tq,
    loc_to_vecs,
    make_compound,
    mul_locations,
    rect,
    tq_to_loc,
)
from ocp_tessellate.utils import Color, make_unique

UNSELECTED = 0
SELECTED = 1
EMPTY = 3

PROTOCOL_VERSION = 3


class OcpObject:
    def __init__(
        self,
        kind,
        obj=None,
        ref=None,
        cache_id=None,
        name="Object",
        loc=None,
        color=None,
        width=None,
        show_faces=True,
        show_edges=True,
    ):
        if obj is None and ref is None:
            raise ValueError("Either obj or ref must be provided")

        self.id = None
        self.obj = obj
        self.kind = kind
        self.ref = ref
        self.cache_id = cache_id
        self.name = name
        self.set_states(show_faces, show_edges)
        self.loc = loc
        self.color = color
        if isinstance(color, list):
            self.color = [Color(c) for c in self.color]
        elif color is not None:
            self.color = Color(self.color)
        self.width = width

    def dump(self, ind=0):
        if self.obj is None:
            obj_repl = f"ref={self.ref}"
        else:
            obj_repl = f"class={self.obj.__class__.__name__}"

        return (
            f"{' '*ind}OcpObject name='{self.name}' kind={self.kind}, "
            f"{obj_repl}, "
            f"color={self.color}, loc={loc_to_tq(self.loc)}, "
            f"cache_id={'' if self.cache_id is None else self.cache_id[:10]}..."
        )

    def __repr__(self):
        return self.dump()

    def copy(self):
        return OcpObject(
            self.kind,
            copy_topods_shape(self.obj),
            self.ref,
            self.cache_id,
            self.name,
            copy_location(self.loc),
            Color(self.color),
            self.width,
            self.state_faces,
            self.state_edges,
        )

    def set_states(self, show_faces, show_edges):
        self.state_faces = SELECTED if show_faces else UNSELECTED
        self.state_edges = SELECTED if show_edges else UNSELECTED

    def to_state(self):
        if self.kind in ("solid", "face"):
            return [self.state_faces, self.state_edges]
        else:
            return [EMPTY, SELECTED]

    def collect(self, path, instances, loc, discretize_edges, convert_vertices):
        self.id = f"{path}/{self.name}"
        texture = None

        if loc is None and self.loc is None:
            combined_loc = None
        elif loc is None:
            combined_loc = self.loc
        elif self.loc is None:
            combined_loc = loc
        else:
            combined_loc = loc * self.loc

        if self.kind == "imageface":
            image = {"data": self.image, "format": self.image_type}
            texture = {"image": image, "width": self.width, "height": self.height}
            self.kind = "face"

        if self.kind in ("solid", "face", "shell"):
            return dict(id=self.id, shape=instances[self.ref], loc=combined_loc), {
                "id": self.id,
                "type": "shapes",
                "subtype": self.kind,
                "name": self.name,
                "shape": {"ref": self.ref},
                "state": self.to_state(),
                "color": self.color.web_color,
                "alpha": self.color.a,
                "texture": texture,
                "loc": None if self.loc is None else loc_to_tq(self.loc),
                "renderback": self.kind == "face",
                "accuracy": None,
                "bb": None,
            }

        elif self.kind in ("edge", "vertex"):
            convert = convert_vertices if self.kind == "vertex" else discretize_edges
            if not isinstance(self.obj, list):
                self.obj = [self.obj]
            values, bb = convert(self.obj, self.name, self.id)

            if isinstance(self.color, (list, tuple)):
                color = [c.web_color for c in self.color]
            else:
                color = self.color.web_color

            result = dict(id=self.id, shape=self.obj, loc=None), {
                "id": self.id,
                "type": "edges" if self.kind == "edge" else "vertices",
                "name": self.name,
                "shape": values,
                "state": self.to_state(),
                "color": color,
                "loc": None if self.loc is None else loc_to_tq(self.loc),
                "bb": bb,
            }
            if self.kind == "edge":
                result[1]["width"] = self.width
            else:
                result[1]["size"] = self.width
            return result

        else:
            raise NotImplementedError(f"Kind {self.kind} not implemented")


class OcpGroup:
    def __init__(self, objs=None, name="Group", loc=None):
        self.id = None
        self.objects = [] if objs is None else objs
        self.name = name
        self.kind = "group"
        self.loc = loc

    def dump(self, ind=0):
        result = f"{' '*ind}OcpGroup('{self.name}', loc={loc_to_tq(self.loc)}\n"
        for obj in self.objects:
            result += obj.dump(ind + 4) + "\n"
        return result + f"{' '*ind})"

    def __repr__(self):
        return self.dump()

    @property
    def length(self):
        return len(self.objects)

    def add(self, *objs):
        for obj in objs:
            self.objects.append(obj)

    def make_unique_names(self):
        if self.length > 1:
            names = make_unique([obj.name for obj in self.objects])
            for obj, name in zip(self.objects, names):
                obj.name = name
        return self

    def cleanup(self):
        if self.length == 1:
            if isinstance(self.objects[0], OcpObject):
                self.loc = mul_locations(self.loc, self.objects[0].loc)
            return self.objects[0]

        return self

    def to_state(self, parents=None):
        parents = parents or ()
        result = {}
        for i, obj in enumerate(self.objects):
            if isinstance(obj, OcpGroup):
                for k, v in obj.to_state((*parents, i)).items():
                    result[k] = v
            else:
                result[str(obj.id)] = obj.to_state()
        return result

    def count_shapes(self):
        def c(pg):
            count = 0
            for p in pg.objects:
                if isinstance(p, OcpGroup):
                    count += c(p)
                else:
                    count += 1
            return count

        return c(self)

    def collect(
        self, path, instances, loc=None, discretize_edges=None, convert_vertices=None
    ):
        self.id = f"{path}/{self.name}"

        if loc is None and self.loc is None:
            combined_loc = None
        elif loc is None:
            combined_loc = self.loc
        elif self.loc is None:
            combined_loc = loc
        else:
            combined_loc = loc * self.loc

        result = {
            "version": PROTOCOL_VERSION,
            "parts": [],
            "loc": None if self.loc is None else loc_to_tq(self.loc),
            "name": self.name,
            "id": self.id,
        }

        map = {"parts": [], "id": self.id}

        for obj in self.objects:
            mapping, mesh = obj.collect(
                self.id, instances, combined_loc, discretize_edges, convert_vertices
            )
            result["parts"].append(mesh)
            map["parts"].append(mapping)
        return map, result


class OcpWrapper:

    def __init__(
        self,
        objs,
        kind,
        name,
        color,
        loc=None,
        width=None,
        show_edges=True,
        show_faces=True,
    ):
        self.objs = objs
        self.kind = kind
        self.name = name
        self.color = color
        self.loc = identity_location() if loc is None else loc
        self.width = width
        self.show_edges = show_edges
        self.show_faces = show_faces

    def to_ocp(self):
        return OcpObject(
            self.kind,
            self.objs,
            name=self.name,
            loc=self.loc,
            color=self.color,
            width=self.width,
            show_edges=self.show_edges,
            show_faces=self.show_faces,
        )


class CoordAxis(OcpWrapper):
    def __init__(self, name, origin, z_dir, color=None, size=1):
        if color is None:
            color = Color("black")
        o, x, y, z = axis_to_vecs(origin, z_dir)
        edge = line(o, o + size * z)
        f = 0.8 + math.atan(size * 0.6) / (math.pi / 2) / 6
        dz = size * f * z
        dx = size * ((1 - f) / 4) * x
        dy = size * ((1 - f) / 4) * y
        a = [
            line(o + size * z, o + dz - dx),
            line(o + size * z, o + dz + dx),
            line(o + size * z, o + dz - dy),
            line(o + size * z, o + dz + dy),
            line(o + dz - dx, o + dz + dx),
            line(o + dz - dy, o + dz + dy),
            line(o + dz - dy, o + dz + dx),
            line(o + dz - dy, o + dz - dx),
            line(o + dz + dy, o + dz + dx),
            line(o + dz + dy, o + dz - dx),
        ]

        super().__init__([edge] + a, "edge", name, color, width=2)


class CoordSystem(OcpWrapper):
    def __init__(self, name, origin, x_dir, z_dir, size=1):
        o, x, y, z = loc_to_vecs(origin, x_dir, z_dir)
        x_edge = line(o, o + size * x)
        y_edge = line(o, o + size * y)
        z_edge = line(o, o + size * z)

        colors = [Color("red"), Color("green"), Color("blue")]
        super().__init__([x_edge, y_edge, z_edge], "edge", name, colors, width=2)


class ImageFace(OcpWrapper):
    def __init__(
        self,
        image_path,
        scale=1.0,
        origin_pixels=(0, 0),
        location=None,
        name="ImageFace",
    ):
        self.image_width, self.image_height = imagesize.get(image_path)
        x = origin_pixels[0]
        y = self.image_height - origin_pixels[1]

        if isinstance(scale, (int, float)):
            scale = (scale, scale)

        ws = self.image_width * scale[0]
        hs = self.image_height * scale[1]
        xs = x * scale[0]
        ys = y * scale[1]

        plane = rect(ws, hs)
        loc = location.wrapped if hasattr(location, "wrapped") else location
        o = tq_to_loc((ws / 2 - xs, hs / 2 - ys, 0), (0, 0, 0, 1))
        loc = loc * o if loc is not None else o

        super().__init__(
            [plane], "imageface", name, Color("white"), show_edges=True, loc=loc
        )

        with open(image_path, "rb") as f:
            self.image = base64.b64encode(f.read()).decode("utf-8")
            self.image_type = image_path.split(".")[-1]

        self.width = ws
        self.height = hs

    def to_ocp(self):
        result = super().to_ocp()
        result.image = self.image
        result.image_type = self.image_type
        result.image_width = self.image_width
        result.image_height = self.image_height
        result.width = self.width
        result.height = self.height
        return result


class OCP_Part(OcpWrapper):
    def __init__(
        self,
        shape,
        name="Part",
        color=None,
        show_faces=True,
        show_edges=True,
    ):
        if color is None:
            color = Color(get_default("default_color"))

        super().__init__(
            [shape], "solid", name, color, show_faces=show_faces, show_edges=show_edges
        )


class OCP_Faces(OCP_Part):
    def __init__(
        self,
        faces,
        name="Faces",
        color=None,
        show_faces=True,
        show_edges=True,
    ):
        if color is None:
            color = Color("Violet")
        obj = make_compound(faces)
        super().__init__(obj, name, color, show_faces, show_edges)


class OCP_Edges(OcpWrapper):
    def __init__(self, edges, name="Edges", color=None, width=1):
        if color is None:
            color = Color("MediumOrchid")
        super().__init__(edges, "edge", name, color, width=width)
        self.width = 2


class OCP_Vertices(OcpWrapper):
    def __init__(self, vertices, name="Vertices", color=None, size=1):
        if color is None:
            color = Color("MediumOrchid")
        super().__init__(vertices, "vertex", name, color, width=size)
        self.width = 6


class OCP_PartGroup(list):
    def __init__(self, objects, name="Group", loc=None):
        super().__init__(objects)
        self.objs = objects
        self.loc = loc
        self.name = name
        self.index = 0

    def __iter__(self):
        self.index = 0
        return self

    def __next__(self):
        if self.index < len(self.objs):
            result = self.objs[self.index]
            self.index += 1
            return result
        else:
            raise StopIteration

    def __getitem__(self, i):
        return self.objs[i]

    def __len__(self):
        return len(self.objs)

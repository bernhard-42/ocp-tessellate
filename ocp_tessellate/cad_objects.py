from ocp_tessellate.ocp_utils import (
    axis_to_vecs,
    loc_to_vecs,
    line,
    make_compound,
    loc_to_tq,
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
        alpha=None,
        width=None,
        show_faces=True,
        show_edges=True,
    ):
        if obj is None and ref is None:
            raise ValueError("Either obj or ref must be provided")
        self.obj = obj
        self.kind = kind
        self.ref = ref
        self.cache_id = cache_id
        self.name = name
        self.set_states(show_faces, show_edges)
        self.loc = loc
        self.color = color
        self.alpha = alpha
        if isinstance(color, list):
            self.color = [Color(c).web_color for c in self.color]
        elif color is not None:
            self.color = Color(self.color).web_color
        self.width = width

    def dump(self, ind=0):
        if self.obj is None:
            obj_repl = f"ref={self.ref}"
        else:
            obj_repl = f"class={self.obj.__class__.__name__}"

        return (
            f"{' '*ind}OcpObject('{self.name}' ({self.kind}), "
            f"{obj_repl}, "
            f"color={self.color}, loc={loc_to_tq(self.loc)})"
        )

    def set_states(self, show_faces, show_edges):
        self.state_faces = SELECTED if show_faces else UNSELECTED
        self.state_edges = SELECTED if show_edges else UNSELECTED

    def to_state(self):
        if self.kind in ("solid", "face"):
            return [self.state_faces, self.state_edges]
        else:
            return [EMPTY, SELECTED]

    def collect(self, path, instances, loc):
        self.id = f"{path}/{self.name}"
        texture = None
        combined_loc = loc
        if self.loc is not None and combined_loc is not None:
            combined_loc = combined_loc * self.loc

        if self.kind in ("solid", "face"):
            return dict(id=self.id, shape=instances[self.ref], loc=combined_loc), {
                "id": self.id,
                "type": "shapes",
                "subtype": self.kind,
                "name": self.name,
                "shape": {"ref": self.ref},
                "color": self.color,
                "texture": texture,
                "alpha": self.alpha,
                "loc": None if self.loc is None else loc_to_tq(self.loc),
                "renderback": self.kind == "face",
                "accuracy": None,
                "bb": None,
            }
        else:
            raise NotImplementedError(f"Kind {self.kind} not implemented")

    def __repr__(self):
        return self.dump()


class OcpGroup:
    def __init__(self, objs=None, name="Group", loc=None):
        self.objects = [] if objs is None else objs
        self.name = name
        self.loc = loc

    def dump(self, ind=0):
        result = f"{' '*ind}OcpGroup('{self.name}', loc={loc_to_tq(self.loc)}\n"
        for obj in self.objects:
            result += obj.dump(ind + 4) + "\n"
        return result + f"{' '*ind})\n"

    def __repr__(self):
        return self.dump()

    @property
    def length(self):
        return len(self.objects)

    def add(self, *objs):
        for obj in objs:
            self.objects.append(obj)

    def make_unique_names(self):
        names = make_unique([obj.name for obj in self.objects])
        for obj, name in zip(self.objects, names):
            obj.name = name

    def to_state(self, parents=None):  # pylint: disable=arguments-differ
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
        self,
        path,
        instances,
        loc=None,
    ):
        self.id = f"{path}/{self.name}"

        if loc is None and self.loc is None:
            combined_loc = None
        elif loc is None:
            combined_loc = self.loc
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
                self.id,
                instances,
                combined_loc,
            )
            result["parts"].append(mesh)
            map["parts"].append(mapping)
        return map, result


class CoordAxis(OcpObject):
    def __init__(self, name, origin, z_dir, size=1):
        o, x, y, z = axis_to_vecs(origin, z_dir)
        edge = line(o, o + size * z)
        a2 = line(o + size * z, o + size * 0.9 * z - size * 0.025 * x)
        a3 = line(o + size * z, o + size * 0.9 * z + size * 0.025 * x)
        a4 = line(o + size * z, o + size * 0.9 * z - size * 0.025 * y)
        a5 = line(o + size * z, o + size * 0.9 * z + size * 0.025 * y)
        color = Color("black")
        super().__init__(
            make_compound([edge, a2, a3, a4, a5]), name, color=color, width=3
        )


class CoordSystem(OcpObject):
    def __init__(self, name, origin, x_dir, z_dir, size=1):
        o, x, y, z = loc_to_vecs(origin, x_dir, z_dir)
        x_edge = line(o, o + size * x)
        y_edge = line(o, o + size * y)
        z_edge = line(o, o + size * z)

        colors = [Color("red"), Color("green"), Color("blue")]
        super().__init__(
            make_compound([x_edge, y_edge, z_edge]), name, color=colors, width=3
        )


class ImageFace: ...


class OCP_Part: ...


class OCP_Faces: ...


class OCP_Edges: ...


class OCP_Vertices: ...


class OCP_PartGroup: ...

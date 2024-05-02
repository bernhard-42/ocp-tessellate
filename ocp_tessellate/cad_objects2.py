from ocp_tessellate.ocp_utils import (
    axis_to_vecs,
    loc_to_vecs,
    line,
    make_compound,
    loc_to_tq,
)
from ocp_tessellate.utils import Color, make_unique


class OcpObj:
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
    ):
        if obj is None and ref is None:
            raise ValueError("Either obj or ref must be provided")
        self.obj = obj
        self.kind = kind
        self.ref = ref
        self.cache_id = cache_id
        self.name = name
        self.loc = loc
        self.color = color
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
            f"{' '*ind}OcpObj('{self.name}' ({self.kind}), "
            f"{obj_repl}, "
            f"color={self.color}, loc={loc_to_tq(self.loc)})"
        )

    def __repr__(self):
        return self.dump()


class OcpGroup:
    def __init__(self, objs=None, name="Group", loc=None):
        self.objs = [] if objs is None else objs
        self.name = name
        self.loc = loc

    def dump(self, ind=0):
        result = f"{' '*ind}OcpGroup('{self.name}', loc={loc_to_tq(self.loc)}\n"
        for obj in self.objs:
            result += obj.dump(ind + 4) + "\n"
        return result + f"{' '*ind})\n"

    def __repr__(self):
        return self.dump()

    @property
    def length(self):
        return len(self.objs)

    def add(self, *objs):
        for obj in objs:
            self.objs.append(obj)

    def make_unique_names(self):
        names = make_unique([obj.name for obj in self.objs])
        for obj, name in zip(self.objs, names):
            obj.name = name


class CoordAxis(OcpObj):
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


class CoordSystem(OcpObj):
    def __init__(self, name, origin, x_dir, z_dir, size=1):
        o, x, y, z = loc_to_vecs(origin, x_dir, z_dir)
        x_edge = line(o, o + size * x)
        y_edge = line(o, o + size * y)
        z_edge = line(o, o + size * z)

        colors = [Color("red"), Color("green"), Color("blue")]
        super().__init__(
            make_compound([x_edge, y_edge, z_edge]), name, color=colors, width=3
        )

import cadquery as cq
import build123d as bd
from alg123d import *
from cadquery_massembly.build123d import (
    BuildAssembly,
    Mates as b_Mates,
    MAssembly,
    Mates,
)

# %%
import json

from ocp_tessellate.convert import to_assembly
from ocp_tessellate.convert import combined_bb, tessellate_group, get_normal_len
from ocp_tessellate.defaults import get_default, get_defaults, preset
from ocp_tessellate.utils import numpy_to_json

import requests

CMD_PORT = 3939


class Progress:
    def update(self):
        print(".", end="", flush=True)

def send(data, port=None):
    if port is None:
        port = CMD_PORT
    r = requests.post(f"http://127.0.0.1:{port}", json=data)
    if r.status_code != 201:
        print("Error", r.text)

# %%

def convert(*cad_objs, names=None, colors=None, alphas=None, **kwargs):
    part_group = to_assembly(
        *cad_objs,
        names=names,
        colors=colors,
        alphas=alphas,
        render_mates=kwargs.get("render_mates", get_default("render_mates")),
        mate_scale=kwargs.get("mate_scale", get_default("mate_scale")),
        default_color=kwargs.get("default_color", get_default("default_color")),
        show_parent=kwargs.get("show_parent", get_default("show_parent")),
    )

    # Do not send defaults for postion, rotation and zoom unless they are set in kwargs
    config = {
        k: v
        for k, v in get_defaults().items()
        if not k
        in (
            "position",
            "rotation",
            "zoom",
            # controlled by VSCode panel size
            "cad_width",
            "height",
            # controlled by VSCode settings
            "tree_width",
            "theme",
            "control",
            "up",
            "glass",
            "tools",
        )
    }

    for k, v in kwargs.items():
        if k in ["cad_width", "height"]:

            print(
                f"Setting {k} cannot be set, it is determined by the VSCode panel size"
            )

        elif k in [
            "tree_width",
            "theme",
            "control",
            "up",
            "glass",
            "tools",
        ]:
            print(f"Setting {k} can only be set in VSCode config")

        elif v is not None:

            config[k] = v

    shapes, states = tessellate_group(
        part_group, kwargs, Progress(), config.get("timeit")
    )

    config["normal_len"] = get_normal_len(
        preset("render_normals", config.get("render_normals")),
        shapes,
        preset("deviation", config.get("deviation")),
    )

    bb = combined_bb(shapes).to_dict()
    # add global bounding box
    shapes["bb"] = bb

    data = {
        "data": json.loads(
            numpy_to_json(dict(shapes=shapes, states=states))
        ),  # improve de-numpying
        "type": "data",
        "config": config,
        "count": part_group.count_shapes(),
    }
    return data


def show(obj):
    data = convert(obj)
    send(data)


# %%

c = cq.Workplane().box(1, 2, 3)

c_ass = cq.Assembly(c, name="box")

m_ass = MAssembly(c, name=c)

# %%

with bd.BuildPart() as bd_box:
    bd.Box(1, 2, 3)

with bd.BuildPart() as bd_sphere:
    bd.Sphere(1)

with bd.BuildSketch() as bd_circle:
    bd.Circle(1)

with bd.BuildLine() as bd_line:
    bd.Line((0, 0), (1, 1))

bd_compound = bd.Compound.make_compound([bd_box.part, bd_sphere.part])
bd_assembly = bd.Compound(label="assembly", children=[bd_box.part, bd_sphere.part])
bd_solid = bd_box.part
bd_facelist = bd_box.faces()
bd_edgelist = bd_box.edges()
bd_solid = bd_box.solids()[0]
bd_face = bd_box.faces()[2]
bd_edge = bd_box.edges()[0]
bd_vertex = bd_box.vertices()[0]

mixed = bd.Compound.make_compound(bd_box.faces() + bd_box.edges())

# %%

a_box = Box(1, 2, 3)
a_circle = Circle(1)
a_line = Line((0, 0), (1, 1))

# with BuildAssembly(name="a") as b_ass:
#     with b_Mates(a.faces().max()):
#         Part(a, name="a")



# %%

print("\npart:\n")
show(bd_box)

# %%

print("\nsketch:\n")
show(bd_circle)

# %%

print("\nline:\n")
show(bd_line)

# %%

print("\nbd_face:\n")
show(bd_face)

# %%

print("\nbd_edge:\n")
show(bd_edge)

# %%

print("\nbd_vertex:\n")
show(bd_vertex)

# %%


# %%

print("\nbd_facelist:\n")
show(bd_facelist)

# %%

print("\nbd_edgelist:\n")
show(bd_edgelist)

# %%

print("\nbd_compound\n")
show(bd_compound)

# %%


# print("bd_assembly", conv(bd_assembly))

# %%

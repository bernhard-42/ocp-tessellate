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

c_box = cq.Workplane().box(1, 2, 3)
c_sphere = cq.Workplane().sphere(1)

box1 = cq.Workplane("XY").box(10, 20, 30).edges(">X or <X").chamfer(2)
box1.name = "box1"

box2 = cq.Workplane("XY").box(8, 18, 28).edges(">X or <X").chamfer(2)
box2.name = "box2"

box3 = (
    cq.Workplane("XY")
    .transformed(offset=(0, 15, 7))
    .box(30, 20, 6)
    .edges(">Z")
    .fillet(3)
)
box3.name = "box3"

box4 = box3.mirror("XY").translate((0, -5, 0))
box4.name = "box4"

box1 = box1.cut(box2).cut(box3).cut(box4)

c_ass = (
    cq.Assembly(name="ensemble")
    .add(
        box1,
        name="red box",
        color=cq.Color(*Color("#d7191c").percentage, 0.5),
    )  # transparent alpha = 0x80/0xFF
    .add(
        box3,
        name="green box",
        color=cq.Color(*Color("#abdda4").percentage),
    )
    .add(
        box4,
        name="blue box",
        color=cq.Color(43 / 255, 131 / 255, 186 / 255, 0.3),
    )  # transparent, alpha = 0.3
)

show(c_ass)
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

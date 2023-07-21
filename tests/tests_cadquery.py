# %%
import cadquery as cq
from ocp_vscode import show


# %%
# BASIC TESTS

b = cq.Workplane().box(1, 2, 3).fillet(0.1)

show(b)
# %%
show(b.faces())
# %%
show(b.faces("|Z"), show_parent=True)
# %%
show(b.edges("|Z"), show_parent=True)
# %%
show(b.vertices(), show_parent=True)
# %%
show(b.faces("|Z"), b.edges("|Z"), b.vertices())
# %%
show(b, b.edges(), b.vertices())
# %%
show(b.faces().vals())
# %%
show(*b.faces().vals())
# %%
show(b.faces("|Z"), show_parent=True)
# %%
show(b.faces().vals()[7].wrapped, b.edges())
# %%

# ASSEMBLY TEST W/O LOCATION

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
        color=cq.Color(215 / 255, 25 / 255, 28 / 255, 0.5),
    )  # transparent alpha = 0x80/0xFF
    .add(
        box3,
        name="green box",
        color=cq.Color(171 / 255, 221 / 255, 164 / 255),
    )
    .add(
        box4,
        name="blue box",
        color=cq.Color(43 / 255, 131 / 255, 186 / 255, 0.3),
    )  # transparent, alpha = 0.3
)

show(c_ass)

# %%

show(box1.vertices(), show_parent=True)


# %%

# Sketch

v1 = cq.Vector()
v2 = cq.Vector(1, 2, 3)

show(v1, v2)

# %%

c = (
    cq.Sketch()
    .segment((0.0, 0), (2.0, 0.0))
    .segment((0.0, 2))
    .close()
    .arc((0.6, 0.6), 0.4, 0.0, 360.0)
    .assemble(tag="face")
    .edges("%LINE", tag="face")
    #    .vertices()
)

show(c)

# %%

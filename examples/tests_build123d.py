# %%
from build123d import *
from ocp_vscode import show

# %%
with BuildPart() as box:
    Box(1, 2, 3)

with BuildPart() as sphere:
    Sphere(1)

with BuildSketch() as circle:
    Circle(1)

with BuildSketch() as rect:
    Rectangle(1, 2)

with BuildLine() as line:
    Line((1, 1), (2, 2))

with BuildLine() as pline:
    Polyline((0, 0), (0, 1), (1, 1))
pline.label = "pline"
# %%

# Parts
box.label = "BOX"
show(box)

# %%
show(box.part, colors=["red"], alphas=[0.6])

# %%
show(box.part.wrapped, colors=["green"], alphas=[0.6])

# %%

show(box, names=["box"])

# %%
show(box.part, names=["red"], colors=["red"], alphas=[0.6])

# %%
show(box.part.wrapped, names=["green"], colors=["green"], alphas=[0.6])

# %%

# Sketches

show(circle)

# %%

show(circle.sketch, colors=["red"], alphas=[0.6])

# %%

show(circle.sketch.wrapped, colors=["green"], alphas=[0.6])

# %%

show(
    circle,
    rect.sketch,
    names=["circle", "rect"],
    colors=["green", "red"],
    alphas=[0.5, 0.8],
    grid=(True, True, True),
)

# %%

# Lines

show(line, names=["line"])

# %%

show(line.line, names=["line"], colors=["red"])

# %%

show(line.line.wrapped, names=["line"], colors=["green"])

# %%

show(line.line, pline, colors=["red", "cyan"])

# %%

show(line.line, pline, names=["red", "cyan"], colors=["red", "cyan"])

# %%

show(line.line.wrapped, pline, colors=["green", "cyan"])

# %%

# ShapeList and Color tests

show(box.edges())

# %%

show(box.edges(), colors=["black"])

# %%

show(*box.edges())

# %%

show(box.faces())

# %%

show(*box.faces(), colors=["red"] * 6, alphas=[0.4] * 6, render_normals=True)

# %%

show(box.vertices(), colors=[(0.0, 0.5, 1.0)], show_parent=True)

# %%

show(
    *box.vertices().sort_by(Axis.X),
    colors=[(1.0, 0.0, 0.0)] * 4 + [(0.0, 0.0, 0.0)] * 4,
)

# %%

show(*box.edges(), *box.faces(), *box.vertices())

# %%

show(box.edges(), box.faces(), box.vertices(), names=["E", "F", "V"])

# %%

# Mixed Compounds

mixed = Compound.make_compound(box.faces() + box.edges())
show(sphere, mixed)


# %%
def axis_symbol(self, l=1) -> Edge:
    edge = Edge.make_line(self.position, self.position + self.direction * 0.95 * l)
    plane = Plane(
        origin=self.position + 0.95 * l * self.direction,
        z_dir=self.direction,
    )
    cone = Solid.make_cone(l / 60, 0, l / 20, plane)
    return Compound.make_compound([edge] + cone.faces())


sym = axis_symbol(Axis.X)
show(box, sym, axes=False, transparent=True)

# %%
compound = Compound.make_compound([box.part, sphere.part])

show(compound)
# %%


def cylinder(radius, height):
    return Solid.make_cylinder(radius, height)


def reg_poly(radius, count):
    with BuildSketch() as s:
        RegularPolygon(radius, count)
    return s.sketch


c = cylinder(2, 0.1)
p = Plane(c.faces().sort_by().last)
r = reg_poly(0.1, 6)

for loc in PolarLocations(1.8, 12).local_locations:
    r_located = r.located(p.location * loc).faces()[0]
    r_extruded = Solid.extrude(r_located, Vector(0, 0, 0.1))
    c = c.fuse(r_extruded)

show(c, timeit=True)

# %%

show(r_located)

# %%

show(r_extruded)

# %%

r = Rectangle(1, 2)
e = r.edges().filter_by(Axis.X)
show(e, show_parent=True)

# %%

v = e[0].vertices()
show(v, show_parent=True)

# %%

b = Box(1, 2, 3)
f = b.faces().sort_by(Axis.Z).last
e = f.edges().sort_by(Axis.X).last
show(e.vertices(), show_parent=True)

# %%

show(b.vertices(), show_parent=True)

# %%

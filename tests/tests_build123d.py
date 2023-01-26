from build123d import *
from cadquery_massembly.build123d import BuildAssembly, Mates
from cq_vscode import show

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

# %%

# Parts

show(box)
# %%
show(
    sphere.part, names=["sphere"], colors=["red"], alphas=[0.5], grid=(True, True, True)
)
# %%
show(box.part.wrapped, transparent=True, grid=(True, True, True))
# %%

# Sketches

show(circle)
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
show(circle.sketch.wrapped, transparent=True, grid=(True, True, True))
# %%

# Lines

show(pline)
# %%
show(line.line, colors=["blue"])
# %%
show(pline.line.wrapped)
# %%

# ShapeList and Color tests

show(box.edges(), colors=["black"])
# %%
show(box.faces())
# %%
show(box.vertices(), colors=[(0.0, 1.0, 1.0)])
# %%
show(*box.vertices(), colors=[(1.0, 0.0, 0.0)] * 4 + [(0.0, 0.0, 0.0)] * 4)
# %%
show(*box.edges())
# %%
show(*box.faces())
# %%
show(*box.vertices())
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
show(box, sym)

# %%
compound = Compound.make_compound([box.part, sphere.part])

show(compound)
# %%

show(*compound)
# %%

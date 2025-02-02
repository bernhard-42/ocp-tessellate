# %%
import copy

from build123d import *
from ocp_vscode import *

from ocp_tessellate.tessellator import cache


def reference(obj, label, loc=None):
    new_obj = copy.copy(obj)
    if label is not None:
        new_obj.label = label
    if loc is None:
        return new_obj
    else:
        return new_obj.move(loc)


# %%

locs = HexLocations(6, 10, 10).local_locations

sphere = Solid.make_sphere(5)
sphere_references = [reference(sphere, label="Sphere", loc=loc) for loc in locs]
assembly = Compound(children=sphere_references)

show(assembly)
# %%

sphere = Solid.make_sphere(4)
spheres = [loc * sphere for loc in locs]
assembly = Compound(children=spheres)

show(assembly)

# %%

s = Sphere(1)
b = Box(1, 2, 3)
b1 = Pos(X=3) * b
b2 = Pos(X=-3) * b

show(
    s,
    b1,
    b2,
    names=["s", "b1", "b2"],
    colors=["red", "green", "blue"],
    alphas=[0.8, 0.6, 0.4],
    timeit=False,
)

# %%
cache.clear()
s = Sphere(1)
s2 = Sphere(1)
b = Box(1, 2, 3)
b1 = reference(b, label="b1", loc=Pos(X=3))
b2 = reference(b, label="b2", loc=Pos(X=-3))

show(
    s,
    b,
    b1,
    b2,
    s2,
    colors=["red", "green", "blue", "cyan", "yellow"],
    alphas=[0.8, 0.6, 0.4, 1.0, 0.2],
    timeit=False,
)
# expected --**c

# %%

b2 = b2 - Pos(X=-3) * Box(5, 0.2, 0.2)

show(
    s,
    b,
    b1,
    b2,
    s2,
    names=["s", "b", "b1", "b2", "s2"],
    colors=["red", "green", "blue", "cyan", "yellow"],
    alphas=[0.8, 0.6, 0.4, 1.0, 0.2],
    timeit=False,
)
# expected -***c
# %%

show(Pos(X=1.5) * b, Pos(X=-1.5) * b, timeit=False)

# %%

b = Box(0.1, 0.1, 1)
c = Cylinder(1, 0.5)
p = Plane(c.faces().sort_by().last)
b = [p * loc * b for loc in PolarLocations(0.7, 12)]
c = Compound(b + [c])

show(c, timeit=False)

# %%

show(*c.solids(), timeit=False)

# %%

b = Box(0.1, 0.1, 1)
c = Cylinder(1, 0.5)
p = Plane(c.faces().sort_by().last)
b = [reference(b, "pillar", p.location * loc) for loc in PolarLocations(0.7, 12)]

show(*b)

# %%
b = Box(0.1, 0.1, 1)
c = Cylinder(1, 0.5)
p = Plane(c.faces().sort_by().last)
b = [copy.copy(b).move(p.location * loc) for loc in PolarLocations(0.7, 12)]

show(*b, timeit=False)


# %%
c = Compound(b + [c])
show(*c.solids(), timeit=False)

# %%

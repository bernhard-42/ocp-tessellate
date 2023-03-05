import copy
from build123d import *
import alg123d as ad
from cq_vscode import show

# %%

Workplanes(Plane.XY).__enter__()

locs = HexLocations(6, 10, 10).local_locations

box = Solid.make_sphere(5)
box_references = [copy.copy(box).locate(loc) for loc in locs]
assembly = Compound(children=box_references)

# %%

show(assembly, timeit=False)

# %%

s = ad.Sphere(1)
b = ad.Box(1, 2, 3)
b1 = b @ ad.Pos(x=3)
b2 = b @ ad.Pos(x=-3)

# %%

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

s = ad.Sphere(1)
b = ad.Box(1, 2, 3)
b1 = b @ ad.Pos(x=3)
b2 = b @ ad.Pos(x=-3)

# %%

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

b2 = b2 - ad.Box(5, 0.2, 0.2) @ ad.Pos(x=-3)

# %%

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

show(b, timeit=False)

# %%

show(b @ ad.Pos(x=1.5), b @ ad.Pos(x=-1.5), timeit=False)


# %%
b = ad.Box(0.1, 0.1, 1)
c = ad.Cylinder(1, 0.5)
p = ad.Plane(c.faces().max())
b = [b @ (p * loc) for loc in ad.PolarLocations(0.7, 12)]
c = ad.Compound.make_compound(b + [c])

# %%

show(c, timeit=False)

# %%

show(*c.solids(), timeit=False)

## %%

from build123d import *
from cq_vscode import show


# %%

# Can't make empty compounds (for now) so start with a small box
c1 = Compound.make_compound([Solid.make_box(0.1, 0.1, 0.1)])
c1.label = "c1"

c2 = Compound.make_compound([Solid.make_box(0.1, 0.1, 0.1)])
c2.label = "c2"

c3 = Compound.make_compound([Solid.make_box(0.1, 0.1, 0.1)])
c3.label = "c3"

# Create some objects to add to the compounds
s1 = Solid.make_box(1, 1, 1).locate(Location((3, 3, 3)))
s1.label = "box"
s1.color = "red"

s2 = Solid.make_cone(2, 1, 2).locate(Location((-3, 3, 3)))
s2.label = "cone"
s2.color = "green"

s3 = Solid.make_cylinder(1, 2).locate(Location((-3, -3, 3)))
s3.label = "cylinder"
s3.color = "blue"

s4 = Solid.make_sphere(2).locate(Location((3, 3, -3)))
s4.label = "sphere"

s5 = Solid.make_torus(3, 1).locate(Location((-3, 3, -3)))
s5.label = "torus"
s5.color = "cyan"

c2.children = [s2, s3]
c3.children = [s4, s5]
c1.children = [s1, c2, c3]

# %%

show(c1)

# %%

show(c2)

# %%

show(c3)

# %%

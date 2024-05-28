# %%
from build123d import *
from ocp_vscode import *

# %%

# Create some objects to add to the compounds
s1 = Solid.make_box(1, 1, 1).move(Location((3, 3, 3)))
s1.label, s1.color = "box", "red"

s2 = Solid.make_cone(2, 1, 2).move(Location((-3, 3, 3)))
s2.label, s2.color = "cone", "green"

s3 = Solid.make_cylinder(1, 2).move(Location((-3, -3, 3)))
s3.label, s3.color = "cylinder", "blue"

s4 = Solid.make_sphere(2).move(Location((3, 3, -3)))
s4.label = "sphere"

s5 = Solid.make_torus(3, 1).move(Location((-3, 3, -3)))
s5.label, s5.color = "torus", "cyan"

c2 = Compound(label="c2", children=[s2, s3])
c3 = Compound(label="c3", children=[s4, s5])
c1 = Compound(label="c1", children=[s1, c2, c3])


# %%

show(s1, s2, s3, s4, s5)

# %%

show(c1, collapse=Collapse.NONE)

# %%

show(c2)

# %%

show(c3)

# %%

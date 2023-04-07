from ocp_vscode import show
from ocp_tessellate.cad_objects import CoordSystem

c1 = CoordSystem("xyz", (0.1, 0.2, 0.3), X=(0, 1, 0), Z=(1, 0, 0), size=1)

show(c1, axes=True, axes0=True)

# %%

c2 = CoordSystem("xyz 2", (-0.1, -0.2, -0.3), X=(0, 0, 1), Z=(-1, 0, 0), size=1)

show(c1, c2, axes=True, axes0=True)

# %%

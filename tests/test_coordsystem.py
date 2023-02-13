from cq_vscode import show
from ocp_tessellate.cad_objects import CoordSystem

c = CoordSystem("xyz", (0.1, 0.2, 0.3), (1, 0, 0), (0, 1, 0), (0, 0, 1), 1)

show(c, axes=True, axes0=True)

# %%

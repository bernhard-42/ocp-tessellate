from cq_vscode import show
from ocp_tessellate.cad_objects import CoordSystem

c = CoordSystem((1, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1), 1)

show(c)

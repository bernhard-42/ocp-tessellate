# %%
from build123d import *
from ocp_viewer_core.viewer import set_defaults, show

from ocp_tessellate.cad_objects import CoordAxis, CoordSystem

c1 = CoordSystem("xyz", (0.1, 0.2, 0.3), x_dir=(0, 1, 0), z_dir=(1, 0, 0), size=1)

show(c1, axes=True, axes0=True)

# %%

c2 = CoordSystem("xyz 2", (-0.1, -0.2, -0.3), x_dir=(0, 0, 1), z_dir=(-1, 0, 0), size=1)

show(c1, c2, axes=True, axes0=True)

# %%

ax = CoordAxis("ax", (0.1, 0.2, 0.3), z_dir=(1, 0, 0))
ay = CoordAxis("ay", (0.1, 0.2, 0.3), z_dir=(0, 1, 0))
az = CoordAxis("az", (0.1, 0.2, 0.3), z_dir=(0, 0, 1))
show(ax, ay, az)
# %%

set_defaults(helper_scale=5)
loc = Location((1, 2, 3), (10, 20, 30))

ox = list(loc.x_axis.position)
dx = list(loc.x_axis.direction)
oy = list(loc.y_axis.position)
dy = list(loc.y_axis.direction)
oz = list(loc.z_axis.position)
dz = list(loc.z_axis.direction)

c = CoordSystem("xyz", ox, x_dir=dx, z_dir=dz, size=2)
ax = CoordAxis("ax", ox, z_dir=dx)
ay = CoordAxis("ay", oy, z_dir=dy)
az = CoordAxis("az", oz, z_dir=dz)

show(c, ax, ay, az)

# %%
p = Plane(Location((1, 2, 3), (10, 20, 30)))
show(p, helper_scale=0.2)
# %%
b = Box(1, 2, 3)
show(b, Location(), helper_scale=0.5)
# %%

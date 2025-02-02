# %%
from ocp_vscode import show

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

from build123d import *
from ocp_vscode import set_defaults

set_defaults(helper_scale=5)
loc = Location((1, 2, 3), (10, 20, 30))

ox = loc.x_axis.position.to_tuple()
dx = loc.x_axis.direction.to_tuple()
oy = loc.y_axis.position.to_tuple()
dy = loc.y_axis.direction.to_tuple()
oz = loc.z_axis.position.to_tuple()
dz = loc.z_axis.direction.to_tuple()

c = CoordSystem("xyz", ox, x_dir=dx, z_dir=dz, size=2)
ax = CoordAxis("ax", ox, z_dir=dx)
ay = CoordAxis("ay", oy, z_dir=dy)
az = CoordAxis("az", oz, z_dir=dz)

show(c, ax, ay, az)

# %%
p = Plane(Location((1, 2, 3), (10, 20, 30)), helper_scale=1)
show(p)
# %%
b = Box(1, 2, 3)
show(b, Location(), helper_scale=0.5)
# %%

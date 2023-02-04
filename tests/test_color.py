from OCP.Quantity import Quantity_ColorRGBA
import cadquery as cq
import build123d as bd
import alg123d as ad
from ocp_tessellate.utils import Color
from ocp_tessellate.ocp_utils import get_rgba
from cq_vscode import show, show_object, reset_show, set_port, set_defaults, get_defaults
set_port(3939)


# %%

print(get_rgba(cq.Color("red")))

# %%
print(get_rgba(cq.Color("green"), 0.5))

# %%
print(get_rgba(ad.Color("red")))

# %%
print(get_rgba(bd.Color("blue")))

# %%
print(get_rgba(Color("red")))

# %%
print(get_rgba(cq.Color("red").wrapped))

# %%

print(get_rgba("red"))

# %%

s = ad.Sphere(1)
b = ad.Box(1,2,3) @ ad.Pos(x=3)

show(s, b, names=["s", "b"], colors=["red", "green"], alphas=[0.8, 0.6])


# %%




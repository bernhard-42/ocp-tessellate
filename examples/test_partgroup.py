# %%
import cadquery as cq
from ocp_vscode import *
from ocp_tessellate import Part, PartGroup, OCP_Part


def ring(inner_radius, outer_radius, width):
    ring = (
        cq.Workplane(origin=(0, 0, -width / 2))
        .circle(outer_radius)
        .circle(inner_radius)
        .extrude(width)
    )
    return ring


tol = 0.05
ball_diam = 5

r1, r2, r3, r4 = 4, 6, 8, 10
r5 = (r3 + r2) / 2
inner_ring = ring(r1, r2, ball_diam)
outer_ring = ring(r3, r4, ball_diam)

torus = cq.CQ(cq.Solid.makeTorus(r5, ball_diam / 2 + tol))
ball = cq.Workplane().sphere(ball_diam / 2)

inner = inner_ring.cut(torus, clean=False)
outer = outer_ring.cut(torus, clean=False)

show(
    PartGroup(
        [Part(ball, "ball", color="black"), Part(inner, "inner"), Part(outer, "outer")],
        "bearing",
    )
)

# %%

show(Part(ball))
# %%

show(OCP_Part([ball.val().wrapped]))
# %%

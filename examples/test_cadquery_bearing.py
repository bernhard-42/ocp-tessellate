from collections import OrderedDict as odict

import cadquery as cq
from cadquery_massembly import MAssembly, Mate
from ocp_vscode import *
from ocp_vscode.animation import Animation

from ocp_tessellate.utils import Color

set_defaults(axes=False, axes0=True, edge_accuracy=0.01, helper_scale=1)


## Parts


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

inner = inner_ring.cut(torus)
outer = outer_ring.cut(torus)

show(ball, inner, outer)


## Assembly

number_balls = 6
balls = ["ball_%d" % i for i in range(number_balls)]


def create_bearing():
    L = lambda *args: cq.Location(cq.Vector(*args))
    C = lambda name: Color(name).web_color

    assy = MAssembly(outer, loc=L(0, 0, ball_diam / 2), name="outer", color=C("orange"))
    assy.add(inner, loc=L(20, 0, 0), name="inner", color=C("orange"))
    for i in range(number_balls):
        assy.add(ball, loc=L(6 * i, 20, 0), name=balls[i], color=C("black"))

    return assy


bearing = create_bearing()
show(bearing)

## Mates


bearing.mate("outer@faces@<Z", name="outer", origin=True)
bearing.mate("inner@faces@<Z", name="inner", origin=True)

for i in range(number_balls):
    bearing.mate(
        balls[i], Mate(), name=balls[i], origin=True
    )  # the default Mate is sufficient
    bearing.mate(
        "inner@faces@<Z",
        name="inner_%d" % i,
        transforms=odict(rz=i * 60, tx=r5, tz=-ball_diam / 2),
    )

show(bearing, render_mates=True)


bearing.assemble("inner", "outer")

for i in range(number_balls):
    bearing.assemble(balls[i], "inner_%d" % i)

show(bearing, render_mates=True)

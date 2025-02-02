# %%
import cadquery as cq
from cadquery_massembly import MAssembly
from ocp_vscode import *
from ocp_vscode.animation import Animation

from ocp_tessellate.utils import Color

set_defaults(axes=True, axes0=True, helper_scale=4)

from math import cos, sin

import numpy as np

## Disk and Arm

r_disk = 100
dist_pivot = 200


def angle_arm(angle_disk):
    ra = np.deg2rad(angle_disk)
    v = np.array((dist_pivot, 0)) - r_disk * np.array((cos(ra), sin(ra)))
    return np.rad2deg(np.arctan2(*v[::-1]))


## Assembly

thickness = 5
nr = 5

disk = cq.Workplane().circle(r_disk + 2 * nr).extrude(thickness)
nipple = cq.Workplane().circle(nr).extrude(thickness)
disk = disk.cut(nipple).union(nipple.translate((r_disk, 0, thickness)))

pivot_base = cq.Workplane().circle(2 * nr).extrude(thickness)
base = (
    cq.Workplane()
    .rect(6 * nr + dist_pivot, 6 * nr)
    .extrude(thickness)
    .translate((dist_pivot / 2, 0, 0))
    .union(nipple.translate((dist_pivot, 0, thickness)))
    .union(pivot_base.translate((0, 0, thickness)))
    .union(nipple.translate((0, 0, 2 * thickness)))
    .edges("|Z")
    .fillet(3)
)
base.faces(">Z[-2]").wires(cq.NearestToPointSelector((dist_pivot + r_disk, 0))).tag(
    "mate"
)

slot = (
    cq.Workplane()
    .rect(2 * r_disk, 2 * nr)
    .extrude(thickness)
    .union(nipple.translate((-r_disk, 0, 0)))
    .union(nipple.translate((r_disk, 0, 0)))
    .translate((dist_pivot, 0, 0))
)

arm = (
    cq.Workplane()
    .rect(4 * nr + (r_disk + dist_pivot), 4 * nr)
    .extrude(thickness)
    .edges("|Z")
    .fillet(3)
    .translate(((r_disk + dist_pivot) / 2, 0, 0))
    .cut(nipple)
    .cut(slot)
)
arm.faces(">Z").wires(cq.NearestToPointSelector((0, 0))).tag("mate")

show(
    disk,
    base.translate((0, -1.5 * r_disk, 0)),
    arm.translate((0, 1.5 * r_disk, 0)),
)

## Define assembly


def create_disk_arm():
    L = lambda *args: cq.Location(cq.Vector(*args))
    C = lambda name: Color(name).web_color

    return (
        MAssembly(base, name="base", color=C("silver"), loc=L(-dist_pivot / 2, 0, 0))
        .add(
            disk,
            name="disk",
            color=C("MediumAquaMarine"),
            loc=L(r_disk, -1.5 * r_disk, 0),
        )
        .add(arm, name="arm", color=C("orange"), loc=L(0, 10 * nr, 0))
    )


## Define mates

from collections import OrderedDict as odict

disk_arm = create_disk_arm()

disk_arm.mate("base?mate", name="disk_pivot", origin=True, transforms=odict(rz=180))
disk_arm.mate("base@faces@>Z", name="arm_pivot")
disk_arm.mate("disk@faces@>Z[-2]", name="disk", origin=True)
disk_arm.mate("arm?mate", name="arm", origin=True)

show(disk_arm, render_mates=True)


## Relocate and assemble

# ensure all parts are relocated so that the origin mates is the part origin
disk_arm.relocate()

# assemble each part
disk_arm.assemble("arm", "arm_pivot")
disk_arm.assemble("disk", "disk_pivot")

d = show(disk_arm, render_mates=True, axes=False)


## Animate

animation = Animation(disk_arm)

times = np.linspace(0, 5, 181)
disk_angles = np.linspace(0, 360, 181)
arm_angles = [angle_arm(d) for d in disk_angles]

# move disk
# Note, the selector must follow the path in the CAD view navigation hierarchy
animation.add_track(f"/base/disk", "rz", times, disk_angles)

# move arm
animation.add_track(f"/base/arm", "rz", times, arm_angles)

animation.animate(speed=2)

# %%
import numpy as np
from build123d import *
from ocp_vscode import *
from ocp_vscode.animation import Animation

from bd_animation import AnimationGroup, clone, normalize_track

set_defaults(render_joints=True, helper_scale=8)
thickness = 2
height = 40
width = 65
length = 100
diam = 4
tol = 0.05


# %% Base and top


class Base(Part):
    hinge_x1, hinge_x2 = 0.63, 0.87

    hinges_holes = {
        "right_front": Location((-hinge_x1 * width, -hinge_x1 * length), (0, 0, 195)),
        "right_middle": Location((-hinge_x2 * width, 0), (0, 0, 180)),
        "right_back": Location((-hinge_x1 * width, hinge_x1 * length), (0, 0, 165)),
        "left_front": Location((hinge_x1 * width, -hinge_x1 * length), (0, 0, -15)),
        "left_middle": Location((hinge_x2 * width, 0), (0, 0, 0)),
        "left_back": Location((hinge_x1 * width, hinge_x1 * length), (0, 0, 15)),
    }

    stand_holes = {
        "front_stand": Location((0, -0.8 * length), (0, 0, 180)),
        "back_stand": Location((0, 0.75 * length), (0, 0, 0)),
    }

    def __init__(self, label):
        base = extrude(Ellipse(width, length), thickness)
        base -= Pos(Y=-length + 5) * Box(2 * width, 20, 3 * thickness)

        for pos in self.hinges_holes.values():
            base -= pos * Cylinder(
                diam / 2 + tol,
                thickness,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        for pos in self.stand_holes.values():
            base -= pos * Box(width / 2 + 2 * tol, thickness + 2 * tol, 5 * thickness)

        super().__init__(base.wrapped, label=label)

        # Add joints

        for name, edge in self.hinges_holes.items():
            RigidJoint(f"j_{name}", self, edge)

        for name, pos in self.stand_holes.items():
            RigidJoint(f"j_{name}", self, pos * Rot(0, 0, 90))

        center = self.faces().sort_by().last.center_location
        RigidJoint("j_top", self, center * Pos(Z=height + thickness + 2 * tol))
        RigidJoint("j_bottom", self, center)


base = Base("base")
show(base, render_joints=True)

# %% Stands


class Stand(Part):
    def __init__(self, label):
        self.h = 5

        stand = Box(width / 2 + 10, height + 2 * tol, thickness)
        faces = stand.faces().sort_by(Axis.Y)

        t2 = thickness / 2
        w = height / 2 + tol - self.h / 2
        for i in [-1, 1]:
            rect = Pos(0, i * w, t2) * Rectangle(thickness, self.h)
            block = extrude(rect, self.h)

            m = block.edges().group_by()[-1]
            block = chamfer(
                m.sort_by(Axis.Y).first if i == 1 else m.sort_by(Axis.Y).last,
                length=self.h - 2 * tol,
            )

            stand += block

        for plane in [Plane(faces.first), Plane(faces.last)]:
            stand += plane * Box(
                thickness,
                width / 2,
                thickness,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

        super().__init__(stand.wrapped, label=label)

        RigidJoint(
            "j_bottom",
            self,
            self.faces().sort_by(Axis.Y).last.center_location * Rot(0, 180, 0),
        )


stand = Stand("stand")
show(stand, render_joints=True)

# %% Upper Leg


class UpperLeg(Part):
    def __init__(self, label):
        self.l1 = 50
        self.l2 = 80

        leg_hole = Location((self.l2 - 10, 0), (0, 0, 0))

        line = Polyline(
            (0, 0), (0, height / 2), (self.l1, height / 2 - 5), (self.l2, 0)
        )
        line += mirror(line, about=Plane.XZ)
        face = make_face(line)
        upper_leg = extrude(face, thickness, dir=(0, 0, 1))
        upper_leg = fillet(upper_leg.edges().group_by(Axis.X)[-1], radius=4)

        last = upper_leg.edges()
        upper_leg -= leg_hole * Hole(diam / 2 + tol, depth=thickness)
        self.knee_hole = upper_leg.edges().filter_by(GeomType.CIRCLE) - last

        upper_leg += (
            Pos(0, 0, thickness / 2)
            * Rot(90, 0, 0)
            * Cylinder(diam / 2, 2 * (height / 2 + thickness + tol))
        )

        super().__init__(upper_leg.wrapped, label=label)

        RigidJoint(
            "j_knee_front",
            self,
            leg_hole * Rot(180, 0, -75),
        )
        RigidJoint(
            "j_knee_back", self, leg_hole * Pos(0, 0, thickness) * Rot(0, 0, -105)
        )


upper_leg = UpperLeg("upper_leg")
show(upper_leg, render_joints=True)

# %% Lower Leg


class LowerLeg(Part):
    def __init__(self, label):
        self.w = 15
        self.l1 = 20
        self.l2 = 120

        self.leg_hole = Location((self.l1 - 10, 0), (0, 0, 0))

        line = Polyline((0, 0), (self.l1, self.w), (self.l2, 0))
        line += mirror(line, about=Plane.XZ)
        face = make_face(line)
        lower_leg = extrude(face, thickness, dir=(0, 0, 1))
        lower_leg = fillet(lower_leg.edges().filter_by(Axis.Z), radius=4)

        lower_leg -= self.leg_hole * Hole(diam / 2 + tol, depth=thickness)

        super().__init__(lower_leg.wrapped, label=label)


lower_leg = LowerLeg("lower_leg")
show(lower_leg, render_joints=True)

# %% Create objects

base = Base("base")
stand = Stand("stand")
upper_leg = UpperLeg("upper_leg")
lower_leg = LowerLeg("lower_leg")

# %% Lower leg AnimationGroup

lower_leg_g = AnimationGroup(
    children={"lower_leg": clone(lower_leg, origin=lower_leg.leg_hole)},
    label=f"lower_leg",
)
RevoluteJoint("j_front", lower_leg_g, axis=Axis.Z)
RevoluteJoint("j_back", lower_leg_g, axis=-Axis.Z.located(Pos(0, 0, thickness)))

show(lower_leg_g, render_joints=True)

# %% Leg AnimationGroup

origin = upper_leg.faces().sort_by(Axis.Y)[-1].location

leg_g = {}
for name, orient in (("right", "front"), ("left", "back")):
    leg_g[name] = AnimationGroup(
        children={
            "upper_leg": clone(upper_leg, origin=origin),
            "lower_leg": clone(lower_leg_g),
        },
        label=f"{name}_leg",
        assemble=[(f"upper_leg:j_knee_{orient}", f"lower_leg:j_{orient}")],
    )
    u_leg = leg_g[name][f"/{name}_leg/upper_leg"]
    axis = -u_leg.faces().sort_by(Axis.Z)[0].center_location.z_axis
    RevoluteJoint("j_hinge", leg_g[name], axis=axis)

show(leg_g["left"], leg_g["right"], render_joints=True)

# %% Hexapod AnimationGroup
hexapod = AnimationGroup(
    children={
        "bottom": clone(base, color="grey"),
        "top": clone(base, color="lightgray"),
        "front_stand": clone(stand, color="skyblue"),
        "back_stand": clone(stand, color="skyblue"),
        "left_front_leg": clone(leg_g["left"]),
        "left_middle_leg": clone(leg_g["left"]),
        "left_back_leg": clone(leg_g["left"]),
        "right_front_leg": clone(leg_g["right"]),
        "right_middle_leg": clone(leg_g["right"]),
        "right_back_leg": clone(leg_g["right"]),
    },
    label="hexapod",
    assemble=(
        ("bottom:j_top", "top:j_bottom"),
        ("bottom:j_front_stand", "front_stand:j_bottom"),
        ("bottom:j_back_stand", "back_stand:j_bottom"),
        ("bottom:j_right_front", "right_front_leg:j_hinge"),
        ("bottom:j_right_middle", "right_middle_leg:j_hinge"),
        ("bottom:j_right_back", "right_back_leg:j_hinge"),
        ("bottom:j_left_front", "left_front_leg:j_hinge"),
        ("bottom:j_left_middle", "left_middle_leg:j_hinge"),
        ("bottom:j_left_back", "left_back_leg:j_hinge"),
    ),
)

print(hexapod.show_topology())
show(hexapod, render_joints=True)


# %% Animation


def time_range(end, count):
    return np.linspace(0, end, count + 1)


def vertical(count, end, offset, reverse):
    s = -1 if reverse else 1
    ints = [min(180, (90 + i * (360 // count)) % 360) for i in range(count)]
    heights = [s * round(20 * np.sin(np.deg2rad(x) - 15), 1) for x in ints]
    heights.append(heights[0])
    return time_range(end, count), heights[offset:] + heights[1 : offset + 1]


def horizontal(end, reverse):
    horizontal_angle = 25
    angle = horizontal_angle if reverse else -horizontal_angle
    return time_range(end, 4), [0, angle, 0, -angle, 0]


animation = Animation(hexapod)

for name in Base.hinges_holes.keys():
    times, values = horizontal(4, "middle" not in name)
    animation.add_track(f"/hexapod/{name}_leg", "rz", times, normalize_track(values))

    times, values = vertical(8, 4, 0 if "middle" in name else 4, "left" in name)
    animation.add_track(
        f"/hexapod/{name}_leg/lower_leg", "rz", times, normalize_track(values)
    )

animation.animate(2)

# %%

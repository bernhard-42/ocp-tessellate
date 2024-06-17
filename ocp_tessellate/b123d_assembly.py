import copy

import anytree
from build123d import *


def clone(obj, label=None, color=None, location=None):
    new_obj = copy.copy(obj)
    if label is not None:
        new_obj.label = label
    if color is not None:
        new_obj.color = color
    if location is None:
        return new_obj
    else:
        return new_obj.move(location)


class AnimationGroup(Compound):
    def __init__(self, label, children, location=None):
        super().__init__(label=label, children=children)
        self.location = Location() if location is None else location

    def __getitem__(self, path):
        resolver = anytree.Resolver("label")
        name, _, rest = path.strip("/").partition("/")
        if name != self.label:
            raise ValueError(f"Path '{path}' not valid")
        elif rest == "":
            return self

        return resolver.get(self, rest)

    def assemble(
        self, path, joint_name, to_path, to_joint_name, animate=False, **kwargs
    ):
        def _join(obj, path, joint_name):
            if isinstance(obj, AnimationGroup):
                p, j = joint_name.rsplit(":", 1)
                obj = self[f"/{path.strip('/')}/{p.strip('/')}"]
                joint = obj.joints[j]
            else:
                joint = obj.joints[joint_name]
            return joint

        obj = self[path]
        joint = _join(obj, path, joint_name)
        loc = joint.location

        to_obj = self[to_path]
        to_joint = _join(to_obj, to_path, to_joint_name)
        to_loc = to_joint.location

        if isinstance(obj, AnimationGroup):

            if kwargs.get("angle") is not None:
                to_loc = to_loc * Rot(0, 0, -kwargs["angle"])

            # For sub assemblies, the location gets pushed one level up to the assembly layer
            obj.location = to_loc

            # and relocate all children of the parent assembly
            for child in obj.children:
                child.location = loc.inverse() * child.location

        else:
            # else just use connect_to for flat assemblies
            to_joint.connect_to(joint, **kwargs)

import base64
import json
import math
import time
import warnings

import numpy as np
from webcolors import hex_to_rgb, name_to_rgb, rgb_to_hex


def round_sig(x, sig):
    return round(x, sig - int(math.floor(math.log10(abs(x)))) - 1)


def warn(message, warning=RuntimeWarning, when="always"):
    def warning_on_one_line(
        message, category, filename, lineno, file=None, line=None
    ):  # pylint: disable=unused-argument
        return "%s: %s" % (category.__name__, message)

    warn_format = warnings.formatwarning
    warnings.formatwarning = warning_on_one_line
    warnings.simplefilter(when, warning)
    warnings.warn(message + "\n", warning)
    warnings.formatwarning = warn_format
    warnings.simplefilter("ignore", warning)


#
# Color class
#


class Color:
    def __init__(self, color, alpha=1.0):
        self.a = alpha

        # copy the other color values
        if isinstance(color, Color):
            self.r, self.g, self.b, self.a = color.r, color.g, color.b, color.a

        # web color string #rrggbb or #rrggbbaa
        elif isinstance(color, str):
            if color[0] == "#":
                # aa overwrites self.a
                if len(color) > 7:
                    c = hex_to_rgb(color[:7])
                    self.a = int(color[7:9], 16) / 255
                else:
                    c = hex_to_rgb(color)
            else:
                c = name_to_rgb(color)
            self.r = c.red
            self.g = c.green
            self.b = c.blue
        elif isinstance(color, (tuple, list)) and len(color) >= 3:
            rgb = color[:3]
            if any([isinstance(c, float) for c in rgb]) and all(
                [0.0 <= c <= 1.0 for c in rgb]
            ):
                self.r, self.g, self.b = (int(c * 255) for c in rgb)
            elif all([isinstance(c, int) and (0 <= c <= 255) for c in rgb]):
                self.r, self.g, self.b = rgb
            else:
                self._invalid(color)

            if len(color) == 4:
                self.a = color[3] if color[3] <= 1.0 else color[3] / 255

        elif hasattr(color, "wrapped"):
            if hasattr(color, "toTuple"):
                c = color.toTuple()
            else:
                c = list(color)
            self.r = int(c[0] * 255)
            self.g = int(c[1] * 255)
            self.b = int(c[2] * 255)
            self.a = c[3]

        else:
            self._invalid(color)

        if self.a is None:
            self.a = 1.0
        elif self.a > 1.0:
            warn(f"warning: alpha > 1.0 ({self.a}), using alpha=1.0")
            self.a = 1.0

    def __str__(self):
        return f"Color({self.r}, {self.g}, {self.b}, {self.a})"

    def __repr__(self):
        return f"Color(({self.r}, {self.g}, {self.b}, {self.a}))"

    def _invalid(self, color):
        warn(f"warning: {color} is an invalid color, using grey (#aaa)")
        self.r = self.g = self.b = 160
        self.a = 1.0

    @property
    def rgb(self):
        return (self.r, self.g, self.b)

    @property
    def rgba(self):
        return (self.r, self.g, self.b, self.a)

    @property
    def percentage(self):
        return (self.r / 255, self.g / 255, self.b / 255)

    @property
    def web_color(self):
        return rgb_to_hex((self.r, self.g, self.b))


#
# Timer class
#


class Timer:
    def __init__(self, timeit, name, activity, level=0, newline=False):
        if isinstance(timeit, bool):
            self.timeit = 99 if timeit else -1
        else:
            self.timeit = timeit
        self.activity = activity
        self.name = name
        self.level = level
        self.newline = newline
        self.info = ""
        self.start = time.time()

    def __enter__(self):
        if self.newline:
            print("", flush=True)

        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.level <= self.timeit:
            prefix = ""
            if self.level > 0:
                prefix += "| " * self.level

            if self.name != "":
                self.name = f'"{self.name}"'

            print(
                "%8.3f sec: %s%s %s %s"
                % (
                    time.time() - self.start,
                    prefix,
                    self.activity,
                    self.name,
                    self.info,
                ),
                flush=True,
            )


#
# Helpers
#


def get_color(in_color, def_color, alpha):
    color = Color(def_color if in_color is None else in_color)
    if isinstance(alpha, float) and 0 <= alpha < 1.0:
        color.a = alpha
    return color


def make_unique(names):
    found = {}
    unique_names = []
    for name in names:
        if name is None:
            unique_names.append(None)
            continue

        if found.get(name) is None:
            found[name] = 1
            unique_names.append(name)
        else:
            found[name] += 1
            unique_names.append(f"{name}({found[name]})")

    return unique_names


def distance(v1, v2):
    return np.linalg.norm([x - y for x, y in zip(v1, v2)])


def px(w):
    return f"{w}px"


#
# Generic helpers
#


def class_name(obj):
    return obj.__class__.__name__


def type_name(obj):
    return class_name(obj).split("_")[-1]


def explode(edge_list):
    return [[edge_list[i], edge_list[i + 1]] for i in range(len(edge_list) - 1)]


def flatten(nested_list):
    return [y for x in nested_list for y in x]


#
# Serialisation
#


def numpy_to_buffer_json(value):
    def walk(obj):
        if isinstance(obj, np.ndarray):
            if not obj.flags["C_CONTIGUOUS"]:
                obj = np.ascontiguousarray(obj)

            obj = obj.ravel()
            return {
                "shape": obj.shape,
                "dtype": str(obj.dtype),
                "buffer": base64.b64encode(memoryview(obj)).decode(),
                "codec": "b64",
            }
        elif isinstance(obj, (tuple, list)):
            return [walk(el) for el in obj]
        elif isinstance(obj, dict):
            rv = {}
            for k, v in obj.items():
                rv[k] = walk(v)
            return rv
        else:
            return obj

    return walk(value)


def numpy_to_json(obj, indent=None):
    class NumpyArrayEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, np.integer):
                return int(o)
            if isinstance(o, np.floating):
                return float(o)
            if isinstance(o, np.ndarray):
                return o.tolist()

            return super(NumpyArrayEncoder, self).default(o)

    return json.dumps(obj, cls=NumpyArrayEncoder, indent=indent)


#
# Tree search
#


def tree_find_single_selector(tree, selector):
    if tree.name == selector:
        return tree

    for c in tree.children:
        result = tree_find_single_selector(c, selector)
        if result is not None:
            return result
    return None

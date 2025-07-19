## 3.0.16

- Fix the regression to have continue indented to much for the non showable case

## 3.0.15

- Move the "unknown type " warning behind "debug=True" parameter
- Replace hard coded "DEBUG" with parameter "debug"

## 3.0.14

- Fix helix regression

## 3.0.13

- Adapt to CadQuery's change in color from RGB to RGBs
- Support compound of compound of edges

## 3.0.11, 3.0.12

- Support ShapeLists of Compounds
- Support TopoDS_CompSolid

## 3.0.10

- Support both hashing algorithms of OOCT
- Minor adaptations to build123d fixes/changes
- Fix showing assemblies in lists
- Fix detection of empty objects
- Fix exporting simple STEP imports
- Renamed tests and pytests folders


## v3.0.9

- Add support for OCP 7.8.1


## v3.0.8

- Fix regression for handling cadquery wires (wire.edges() returns one edge or one compound)
- Ensure get_face_type and get_edge_type always return int (ocp_utils.py)
- Enable switch from Extent to Size (being prepared for OCCT 7.8)
- Add get_surface and get_curve to ocp_utils.py


## v3.0.7

- none / deployment issues


## v3.0.6

- Migrate to pyproject.toml
- Support latest cadquery Sketch changes


## v3.0.5

- Remove numpy-quaternion dependency to support numpy 1 and 2
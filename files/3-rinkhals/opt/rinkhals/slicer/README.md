# Slicing engine

`CuraEngine` here is **CuraEngine 15.04.6** by Ultimaker, built unchanged as a
static ARM (armhf) binary by `build/slicer/build-curaengine.sh`.

- Source: https://github.com/Ultimaker/CuraEngine/tree/15.04.6
- License: GNU Affero General Public License v3 (the source above, and
  `LICENSE` in it). It is a separate program that the touch UI starts; the rest
  of Boomslang keeps its own license.

The touch UI (`opt/rinkhals/ui/slicer.py`) gives it the settings, the start and
end of a print for each printer, and checks every file it makes before the
file is put with the printer's files.

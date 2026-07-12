# CONFORM Measurement Tool

A Blender add-on for exporting shape-key interpolation measurements and figure outputs.

## Overview

`CONFORM` helps you generate measurement data from mesh shape keys, including:

- width, height, and length in centimeters
- 2D silhouette area from lateral and dorsal orthographic views
- mesh volume and surface area
- optional OBJ export for each interpolation sample
- optional figures generated from exported measurements

## Features

- Select a mesh with shape keys and build a shape-key sequence
- Preview shape key blends
- Choose between `BCS` and `AGE` export modes
- Choose linear, PCHIP, not-a-knot cubic, or natural cubic BCS interpolation
- Automatically place orthographic lateral and dorsal cameras
- Export a CSV file with measurement data
- Render silhouette PNGs for each sample
- Generate SVG figure outputs

## Requirements

- Blender 5.1.0 or newer on Windows x64, Linux x64, or macOS
- Bundled SciPy 1.18.0 and NumPy 2.5.1 wheels provide PCHIP interpolation

## Installation

1. Download the as a ZIP.
2. In Blender, go to `Edit -> Preferences -> Add-ons`.
3. Click `Install from Disk` and select the ZIP Archive.
4. Search for `CONFORM` and enable the addon.
5. The addon will appear in the 3D Viewport sidebar under the CONFORM tab.

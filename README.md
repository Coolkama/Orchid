# Orchid

Experimental graphics and animation sandbox.

Used for testing procedural modelling, rendering, rigging and animation workflows with Blender and related open-source tools.

Work in this repository is experimental and subject to change.

## Current test

The first milestone proves a fully headless Blender workflow on GitHub Actions:

1. GitHub Actions installs Blender on a Linux runner.
2. Blender runs without a graphical interface.
3. A Python script builds a small test scene from scratch.
4. The workflow renders a PNG and exports a GLB file.
5. Both files are uploaded as a short-lived workflow artifact.

No local Blender installation is required to run this test.

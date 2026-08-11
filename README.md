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

The next milestone adds inspection of an externally generated, textured and rigged GLB character. The generic inspection workflow:

1. Imports a repository GLB into headless Blender.
2. Measures mesh, material, texture, armature and animation metadata.
3. Records the full bone hierarchy and mesh-to-armature links.
4. Automatically frames and renders front, 3/4, left, right and back views.
5. Saves an inspection `.blend` and JSON report.
6. Uploads the inspection pack as a GitHub Actions artifact.

The current public test creature is Glimmerkin. Its source model belongs at `assets/models/glimmerkin.glb`; see `assets/models/README.md`.

Run the **Inspect model** workflow manually and provide the repository path to any GLB you want to inspect. This keeps the tooling generic while allowing unusual non-humanoid rigs to be compared consistently.

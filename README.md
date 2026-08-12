# Orchid

Experimental graphics and animation sandbox.

Used for testing procedural modelling, rendering, rigging and animation workflows with Blender and related open-source tools.

Work in this repository is experimental and subject to change.

## Headless Blender pipeline

The first milestone proved a fully headless Blender workflow on GitHub Actions:

1. GitHub Actions installs Blender on a Linux runner.
2. Blender runs without a graphical interface.
3. A Python script builds a small test scene from scratch.
4. The workflow renders a PNG and exports a GLB file.
5. Both files are uploaded as a short-lived workflow artifact.

No local Blender installation is required to run these tests.

## Model inspection

The next milestone added inspection of externally generated, textured and rigged GLB characters. The generic inspection workflow:

1. Imports a repository GLB into headless Blender.
2. Measures mesh, material, texture, armature and animation metadata.
3. Records the full bone hierarchy and mesh-to-armature links.
4. Automatically frames and renders front, 3/4, left, right and back views.
5. Saves an inspection `.blend` and JSON report.
6. Uploads the inspection pack as a GitHub Actions artifact.

The current public test creature is Glimmerkin. Its source model belongs at `assets/models/glimmerkin.glb`; see `assets/models/README.md`.

Run the **Inspect model** workflow manually and provide the repository path to any GLB you want to inspect. This keeps the tooling generic while allowing unusual non-humanoid rigs to be compared consistently.

## Glimmerkin animation diagnostics

Current work is focused on understanding and validating Glimmerkin's existing rig before building further animation behaviour. In particular, the leg diagnostic is designed to establish how the creature's non-humanoid leg bones actually affect the mesh rather than relying on bone names or humanoid assumptions.

The diagnostic pipeline uses `scripts/limijoy_leg_diagnostic.py` with `assets/models/glimmerkin.glb` and runs entirely in headless Blender. It produces controlled stills in `output/limijoy-leg-diagnostic/` so that individual leg controls and their visible effects can be inspected consistently.

The associated GitHub Actions workflow is `.github/workflows/limijoy-leg-diagnostic.yml`. It installs Blender and its required runtime dependencies, including `python3-numpy`, which Blender's GLB importer requires in the Ubuntu runner environment. Diagnostic output is uploaded as the short-lived `limijoy-leg-diagnostic` workflow artifact.

This stage is deliberately diagnostic: the aim is to verify the rig and deformation behaviour first, then use those observations as the basis for Glimmerkin's animation work. No animation behaviour should be inferred solely from conventional humanoid bone expectations.

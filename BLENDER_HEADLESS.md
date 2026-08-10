# Headless Blender CI setup

This repository runs Blender without a desktop UI on a GitHub-hosted Ubuntu runner. This document records the working setup and the problems encountered while establishing it.

## Working runner setup

The workflow uses `ubuntu-latest` and installs Blender plus the runtime libraries required for headless Eevee rendering and glTF/GLB export:

```bash
sudo apt-get update
sudo apt-get install -y \
  blender \
  python3-numpy \
  libegl1 \
  libgl1 \
  libglx-mesa0 \
  libopengl0 \
  mesa-utils
```

The scene script is then run with:

```bash
blender --background --python-exit-code 1 --python scripts/build_scene.py
```

`--background` runs Blender without its graphical interface. `--python-exit-code 1` makes Python script errors fail the CI job instead of allowing an apparently successful workflow.

## Problems discovered

### `scene.world` can be `None`

After:

```python
bpy.ops.wm.read_factory_settings(use_empty=True)
```

a scene may not have a World assigned. Code that immediately accesses `scene.world.color` can therefore fail with:

```text
AttributeError: 'NoneType' object has no attribute 'color'
```

Create and assign a World explicitly before using it:

```python
if scene.world is None:
    scene.world = bpy.data.worlds.new("World")
```

### Eevee needs EGL/OpenGL libraries on the runner

Blender could start headlessly but Eevee failed to initialise when `libEGL.so.1` was unavailable. Installing the Mesa/EGL/OpenGL runtime packages listed above fixed the problem.

Useful diagnostic command:

```bash
ldconfig -p | grep -E 'libEGL.so.1|libGL.so.1|libOpenGL.so.0' || true
```

### glTF/GLB export needs NumPy

Rendering succeeded before GLB export did. Ubuntu's Blender package attempted to load NumPy from the glTF exporter and failed when it was unavailable. Installing `python3-numpy` fixed the export step.

### Blender render-engine names differ by version

Do not assume a particular Eevee identifier. Blender versions use different identifiers, including `BLENDER_EEVEE` and `BLENDER_EEVEE_NEXT`. Scene-generation code should detect/support the installed version rather than hard-code only the newest identifier.

The CI run that established this setup used Blender 4.0.2 from the Ubuntu package repository.

## Expected proof outputs

The current proof script produces an `output/` directory containing:

- `preview.png` — rendered scene preview
- `scene.glb` — exported glTF binary scene
- `scene.blend` — Blender project file

The GitHub Actions workflow uploads the directory as the `orchid-render-proof` artifact and retains it for three days.

## Why this file exists

The setup looks simple after it works, but several failures were environmental rather than modelling errors. Keep this document updated if the runner, Blender version, renderer, export format, or required packages change so future work does not have to rediscover the same requirements.

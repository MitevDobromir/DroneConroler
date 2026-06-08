#!/usr/bin/env python3
"""
sdf_multidrone.py — generate a per-instance, collision-free SDF for the
iris_camera_sonar drone so N copies can coexist in one Gazebo world.

Why not `gz sdf -p`? The standalone `gz sdf` tool does not install the
resource-path find-callback, so it cannot resolve `model://` includes
(it errors with "Tried to use callback in sdf::findFile()"). So instead
of flattening with gz, we compose in Python: read the two real model
files and splice them, leaving the leaf `model://iris_with_standoffs`
include in place — the *running* gz sim server resolves that fine (it
already does for drone 0).

Per-instance composition (instance i > 0):
  - expand the merged `model://iris_with_ardupilot` include in place:
    keep its `model://iris_with_standoffs` include (nested airframe +
    meshes + imu) and copy its plugins (lift-drag, apply-joint-force,
    ArduPilotPlugin)
  - bump the ArduPilot <fdm_port_in> 9002 -> 9002 + 10*i
  - namespace sonar <topic> drone/sonar/* -> drone{i}/sonar/*
  - namespace camera <topic> drone/camera -> drone{i}/camera
  - bump GstCameraPlugin <udp_port> 5600 -> 5600 + i

NOT touched: imuName / jointName / link_name — they are scoped to the
nested iris_with_standoffs model, so they resolve per-spawn regardless
of the top-level entity name.

Instance 0 returns the original template path UNCHANGED, so every
existing single-drone simulation spawns the exact same file.

The composed file still contains one model://iris_with_standoffs
include; spawn it via the running server (gz service .../create with
sdf_filename) so that include resolves. Spawn it under a unique entity
name (e.g. drone{i+1}) via the EntityFactory `name` field — that, not
this file, makes the top-level model name unique.

CLI (run on the VM):
    python3 sdf_multidrone.py <iris_camera_sonar/model.sdf> <instance> [out_dir]
"""
import os
import re
import sys
import copy
import xml.etree.ElementTree as ET


FDM_BASE = 9002
FDM_STEP = 10
CAM_UDP_BASE = 5600
CAM_UDP_STEP = 1
SONAR_PREFIX = 'drone/sonar/'
CAMERA_TOPIC = 'drone/camera'

# Where iris_with_ardupilot (and friends) live, searched after the
# resource-path env vars. Adjust if your layout differs.
_FALLBACK_MODEL_DIRS = [
    '~/ROS2_Tools/ArduPilot/ardupilot_gazebo/models',
    '~/ROS2_Tools/Models',
]


def resolve_model_sdf(model_name: str) -> str:
    """Find <model_name>/model.sdf via the gz resource path, then fallbacks."""
    search_dirs = []
    for var in ('GZ_SIM_RESOURCE_PATH', 'IGN_GAZEBO_RESOURCE_PATH',
                'GAZEBO_MODEL_PATH'):
        for d in os.environ.get(var, '').split(os.pathsep):
            if d:
                search_dirs.append(d)
    for d in _FALLBACK_MODEL_DIRS:
        search_dirs.append(os.path.expanduser(d))

    for d in search_dirs:
        candidate = os.path.join(d, model_name, 'model.sdf')
        if os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        f"Could not locate model '{model_name}' (model.sdf) on "
        f"GZ_SIM_RESOURCE_PATH or fallbacks. Searched: {search_dirs}")


def _included_model_name(include_el) -> str:
    uri = (include_el.findtext('uri') or '').strip()
    return uri.split('model://', 1)[-1].strip('/ ')


def _patch_model(model_el, instance: int):
    """Rewrite fdm port, sonar/camera topics, and camera udp port in place."""
    counts = {'fdm': 0, 'sonar': 0, 'camera': 0, 'udp': 0}

    for el in model_el.iter('fdm_port_in'):
        try:
            base = int((el.text or '').strip())
        except ValueError:
            base = FDM_BASE
        el.text = str(base + FDM_STEP * instance)
        counts['fdm'] += 1

    for el in model_el.iter('topic'):
        t = (el.text or '').strip()
        if t.startswith(SONAR_PREFIX):
            el.text = f'drone{instance}/sonar/' + t[len(SONAR_PREFIX):]
            counts['sonar'] += 1
        elif t == CAMERA_TOPIC:
            el.text = f'drone{instance}/camera'
            counts['camera'] += 1

    for el in model_el.iter('udp_port'):
        try:
            base = int((el.text or '').strip())
        except ValueError:
            base = CAM_UDP_BASE
        el.text = str(base + CAM_UDP_STEP * instance)
        counts['udp'] += 1

    if counts['fdm'] == 0:
        raise ValueError(
            "No <fdm_port_in> found after composition — the "
            "iris_with_ardupilot model did not contribute its ArduPilot "
            "plugin. Check the include resolved to the right file.")
    if counts['sonar'] == 0 and counts['camera'] == 0:
        raise ValueError(
            "No sonar/camera <topic> found — template does not look like "
            "iris_camera_sonar.")
    return counts


def compose_instance_model(template_path: str, instance: int,
                           ardupilot_model_path: str = None) -> str:
    """Build the composed, patched SDF string for instance i > 0."""
    root = ET.parse(template_path).getroot()
    template_model = root.find('model')
    if template_model is None:
        raise ValueError(f"No <model> in {template_path}")
    sdf_version = root.get('version', '1.9')

    new_model = ET.Element(
        'model', {'name': template_model.get('name', 'iris_camera_sonar')})

    for child in list(template_model):
        if child.tag == 'include' and child.get('merge') == 'true':
            # Expand this merged include from the resolved sub-model.
            sub_name = _included_model_name(child)
            ardu_path = ardupilot_model_path or resolve_model_sdf(sub_name)
            ardu_model = ET.parse(ardu_path).getroot().find('model')
            if ardu_model is None:
                raise ValueError(f"No <model> in {ardu_path}")
            # Keep the sub-model's own includes (the leaf airframe) nested,
            # and copy its real elements (plugins / any links / joints).
            for sub in list(ardu_model):
                if sub.tag in ('include', 'plugin', 'link', 'joint', 'frame'):
                    new_model.append(copy.deepcopy(sub))
        else:
            new_model.append(copy.deepcopy(child))

    _patch_model(new_model, instance)

    sdf_root = ET.Element('sdf', {'version': sdf_version})
    sdf_root.append(new_model)
    return "<?xml version='1.0'?>\n" + ET.tostring(sdf_root, encoding='unicode')


def generate_instance_sdf(template_path: str, instance: int,
                          out_dir: str = '/tmp',
                          ardupilot_model_path: str = None) -> str:
    """Return a spawnable SDF path for `instance`.

    instance 0 -> the original template_path, unchanged.
    instance i -> a composed+patched file in out_dir, path returned.
    """
    if not os.path.isfile(template_path):
        raise FileNotFoundError(template_path)
    if instance <= 0:
        return template_path

    sdf_text = compose_instance_model(template_path, instance,
                                      ardupilot_model_path)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'iris_camera_sonar_inst{instance}.sdf')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(sdf_text)
    return out_path


def _main(argv):
    if len(argv) < 3:
        print("usage: sdf_multidrone.py <iris_camera_sonar/model.sdf> "
              "<instance> [out_dir]", file=sys.stderr)
        return 2
    template = argv[1]
    instance = int(argv[2])
    out_dir = argv[3] if len(argv) > 3 else '/tmp'

    path = generate_instance_sdf(template, instance, out_dir)
    print(f"[OK] instance {instance} -> {path}")
    if instance > 0:
        with open(path, encoding='utf-8') as f:
            text = f.read()
        for tag in ('fdm_port_in', 'topic', 'udp_port'):
            for m in re.finditer(rf'<{tag}>([^<]*)</{tag}>', text):
                print(f"   <{tag}>{m.group(1)}</{tag}>")
    return 0


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
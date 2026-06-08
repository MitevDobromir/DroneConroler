#!/usr/bin/env python3
"""
multidrone.py — fleet bring-up for the iris_camera_sonar drone.

Wraps the (now hardware-verified) per-instance scheme into reusable calls
so the GUI Simulation tab and hivemind can spawn N drones without
re-deriving ports. Everything keys off the instance index i with a 10*i
offset (matching launch_sitl.sh and SimDrone):

    instance i  MAVLink udp   SITL TCP   ArduPilot FDM   camera UDP   sonar topics
    ----------  -----------   --------   -------------   ----------   ----------------
    0           14550         5760       9002            5600         /drone/sonar/*
    1           14560         5770       9012            5601         /drone1/sonar/*
    2           14570         5780       9022            5602         /drone2/sonar/*

Spawn uses the SDF from sdf_multidrone.generate_instance_sdf (instance 0
is the untouched original; i>0 is the composed, port/topic-shifted file).

Note on `gz service .../create`: its Boolean reply often times out even
though the entity spawns fine, so spawn success is confirmed by polling
for the drone's own sonar topic rather than trusting the call's return.

CLI (run from a shell that has sourced setup_ardupilot_env.sh, with a
world already running in GUI/sensor mode):

    python3 multidrone.py <world_name> [n]      # default n=2
"""
import os
import sys
import time
import signal
import subprocess

from sdf_multidrone import generate_instance_sdf

ROS2_TOOLS = os.path.expanduser('~/ROS2_Tools')
LAUNCH_SITL = os.path.join(ROS2_TOOLS, 'Scripts', 'launch_sitl.sh')
DEFAULT_TEMPLATE = os.path.join(
    ROS2_TOOLS, 'Models', 'iris_camera_sonar', 'model.sdf')

MAVLINK_BASE = 14550
SITL_TCP_BASE = 5760
FDM_BASE = 9002
CAM_UDP_BASE = 5600
PORT_STEP = 10               # MAVLink / TCP / FDM step per instance
CAM_UDP_STEP = 1             # camera UDP step per instance

# SITL-log fragments that mean "this vehicle is up and talking".
READY_MARKERS = ('online system', 'ArduPilot Ready', 'Detected vehicle')


def ports(instance: int) -> dict:
    """All per-instance ports + the sonar topic prefix, for logging/wiring."""
    return {
        'mavlink_a': MAVLINK_BASE + PORT_STEP * instance,
        'mavlink_b': MAVLINK_BASE + 1 + PORT_STEP * instance,
        'sitl_tcp': SITL_TCP_BASE + PORT_STEP * instance,
        'fdm': FDM_BASE + PORT_STEP * instance,
        'cam_udp': CAM_UDP_BASE + CAM_UDP_STEP * instance,
        'sonar_prefix': sonar_prefix(instance),
    }


def sonar_prefix(instance: int) -> str:
    """Matches SimDrone: bare for instance 0, /drone{i} for i>0."""
    return '/drone/sonar' if instance == 0 else f'/drone{instance}/sonar'


def entity_name(instance: int) -> str:
    """Unique Gazebo entity name. Topics come from the SDF, not this."""
    return f'drone{instance}'


def build_spawn_argv(world: str, sdf_path: str, name: str,
                     x: float, y: float, z: float) -> list:
    req = (f'sdf_filename: "{sdf_path}", name: "{name}", '
           f'pose: {{position: {{x: {x}, y: {y}, z: {z}}}}}')
    return ['gz', 'service', '-s', f'/world/{world}/create',
            '--reqtype', 'gz.msgs.EntityFactory',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '5000', '--req', req]


def build_sitl_argv(instance: int, vehicle: str = 'copter') -> list:
    return ['bash', LAUNCH_SITL, vehicle, str(instance)]


def _spawn_confirmed(topic_list_text: str, instance: int) -> bool:
    return f'{sonar_prefix(instance)}/front' in topic_list_text


def _sitl_ready(log_text: str) -> bool:
    return any(m in log_text for m in READY_MARKERS)


def _gz_topic_list() -> str:
    try:
        r = subprocess.run(['gz', 'topic', '-l'],
                           capture_output=True, text=True, timeout=10)
        return r.stdout or ''
    except Exception:
        return ''


def spawn_instance(world: str, instance: int, x: float, y: float, z: float,
                   template: str = DEFAULT_TEMPLATE,
                   confirm_timeout: float = 15.0) -> tuple:
    """Generate the instance SDF and spawn it; confirm via its sonar topic.

    Returns (ok, name, sdf_path, detail).
    """
    sdf_path = generate_instance_sdf(template, instance)
    name = entity_name(instance)
    argv = build_spawn_argv(world, sdf_path, name, x, y, z)

    # Fire the create. A timeout here is NOT treated as failure — the
    # entity usually spawns anyway; we confirm by topic below.
    try:
        subprocess.run(argv, capture_output=True, text=True, timeout=12)
    except subprocess.TimeoutExpired:
        pass

    deadline = time.time() + confirm_timeout
    while time.time() < deadline:
        if _spawn_confirmed(_gz_topic_list(), instance):
            return True, name, sdf_path, 'sonar topic present'
        time.sleep(1.0)
    return False, name, sdf_path, 'sonar topic never appeared'


def start_sitl(instance: int, vehicle: str = 'copter',
               log_dir: str = '/tmp') -> tuple:
    """Launch launch_sitl.sh for this instance in its own session.

    Returns (popen, log_path). Inherits the current env, so the caller
    must have sourced setup_ardupilot_env.sh.
    """
    log_path = os.path.join(log_dir, f'sitl_{instance}.log')
    log = open(log_path, 'w')
    proc = subprocess.Popen(
        build_sitl_argv(instance, vehicle),
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    return proc, log_path


def bringup(world: str, n: int = 2, spacing: float = 3.0,
            vehicle: str = 'copter', sitl_wait: float = 35.0,
            template: str = DEFAULT_TEMPLATE) -> bool:
    """Spawn n drones, start n SITLs, wait, and report readiness.

    Leaves the SITL processes running on success (returns True) and
    terminates them on Ctrl-C. Returns False if any drone fails to
    spawn or its SITL never reports ready.
    """
    procs = []
    all_ok = True
    try:
        for i in range(n):
            ok, name, sdf, detail = spawn_instance(
                world, i, i * spacing, 0.0, 0.5, template=template)
            p = ports(i)
            print(f"[SPAWN] i={i} name={name} -> "
                  f"{'OK' if ok else 'FAIL'} ({detail})")
            print(f"        sonar {p['sonar_prefix']}/*  fdm {p['fdm']}  "
                  f"mavlink {p['mavlink_a']}  cam_udp {p['cam_udp']}")
            if not ok:
                all_ok = False

        for i in range(n):
            proc, log_path = start_sitl(i, vehicle)
            procs.append((i, proc, log_path))
            print(f"[SITL ] i={i} pid={proc.pid} -> {log_path}")

        print(f"[WAIT ] giving SITL + Gazebo {sitl_wait:.0f}s to connect...")
        time.sleep(sitl_wait)

        for i, proc, log_path in procs:
            try:
                with open(log_path) as f:
                    txt = f.read()
            except OSError:
                txt = ''
            ready = _sitl_ready(txt)
            alive = proc.poll() is None
            print(f"[CHECK] i={i} alive={alive} ready={ready}")
            if not (alive and ready):
                all_ok = False

        print(f"\n[RESULT] {'ALL DRONES UP' if all_ok else 'SOME FAILED — see logs'}")
        if all_ok:
            print("SITLs left running. Ctrl-C here to stop them.")
            while True:
                time.sleep(1)
        return all_ok
    except KeyboardInterrupt:
        print("\n[STOP] terminating SITLs...")
        return all_ok
    finally:
        for i, proc, _ in procs:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                pass


def _main(argv):
    if len(argv) < 2:
        print("usage: multidrone.py <world_name> [n]", file=sys.stderr)
        return 2
    world = argv[1]
    n = int(argv[2]) if len(argv) > 2 else 2
    return 0 if bringup(world, n) else 1


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))

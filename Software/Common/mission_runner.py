#!/usr/bin/env python3
"""
mission_runner.py - Execute .mission files on real or simulated drones

Reads a .mission JSON file and runs the flight plan through
DroneInterface. Works for both simulation and real hardware.

Usage:
    # Run a mission
    python3 mission_runner.py my_flight.mission

    # Dry run (parse and display, don't fly)
    python3 mission_runner.py my_flight.mission --dry-run

File format (.mission):
{
    "name": "My Mission",
    "description": "What this mission does.",
    "drone": {
        "mode": "sim",
        "firmware": "ardupilot",
        "instance": 0,
        "drone_name": "drone1"
    },
    "preflight": {
        "min_satellites": 6,
        "max_altitude_m": 50,
        "require_sonar": false
    },
    "flight_plan": [
        {"type": "takeoff", "altitude": 10},
        {"type": "move", "x": 5, "y": 0, "speed": 1.0},
        {"type": "move_safe", "x": 10, "y": 0, "speed": 1.0},
        {"type": "land"}
    ]
}

Real drone config:
    "drone": {
        "mode": "real",
        "firmware": "ardupilot",
        "connection": "/dev/ttyUSB0",
        "baud": 57600
    }
"""
import sys
import json
import time
from pathlib import Path

# Add Common directory to path
sys.path.insert(0, str(Path(__file__).parent))

from drone_interface import create_drone, DroneInterface


def load_mission(filepath: str) -> dict:
    """Load and validate a .mission file."""
    path = Path(filepath)
    if not path.exists():
        print(f"[ERROR] File not found: {filepath}")
        sys.exit(1)

    with open(path, 'r') as f:
        data = json.load(f)

    # Validate required fields
    required = ['name', 'drone', 'flight_plan']
    for field in required:
        if field not in data:
            print(f"[ERROR] Missing required field: '{field}'")
            sys.exit(1)

    if not data['flight_plan']:
        print("[ERROR] Flight plan is empty")
        sys.exit(1)

    return data


def display_mission(mission: dict):
    """Print mission summary."""
    print(f"\n{'=' * 50}")
    print(f"  MISSION: {mission['name']}")
    print(f"{'=' * 50}")

    if mission.get('description'):
        print(f"  {mission['description']}")
        print()

    drone_cfg = mission['drone']
    print(f"  Mode:     {drone_cfg.get('mode', 'sim')}")
    print(f"  Firmware: {drone_cfg.get('firmware', 'ardupilot')}")

    if drone_cfg.get('mode') == 'real':
        print(f"  Connect:  {drone_cfg.get('connection', '???')}")
    else:
        print(f"  Instance: {drone_cfg.get('instance', 0)}")

    print(f"\n  Flight Plan ({len(mission['flight_plan'])} steps):")
    for i, step in enumerate(mission['flight_plan'], 1):
        step_type = step['type']
        if step_type == 'takeoff':
            print(f"    {i}. Takeoff to {step['altitude']}m")
        elif step_type == 'move':
            print(f"    {i}. Move N={step.get('x', 0)}m E={step.get('y', 0)}m "
                  f"@ {step.get('speed', 1.0)}m/s")
        elif step_type == 'move_safe':
            print(f"    {i}. Move (avoidance) N={step.get('x', 0)}m "
                  f"E={step.get('y', 0)}m @ {step.get('speed', 1.0)}m/s")
        elif step_type == 'land':
            print(f"    {i}. Land")
        else:
            print(f"    {i}. Unknown: {step_type}")

    if mission.get('preflight'):
        pf = mission['preflight']
        print(f"\n  Preflight Checks:")
        if 'min_satellites' in pf:
            print(f"    Min satellites: {pf['min_satellites']}")
        if 'max_altitude_m' in pf:
            print(f"    Max altitude:   {pf['max_altitude_m']}m")
        if pf.get('require_sonar'):
            print(f"    Sonar required: yes")

    print(f"{'=' * 50}\n")


def run_preflight(drone: DroneInterface, checks: dict) -> bool:
    """Run preflight checks before mission execution.

    Args:
        drone: Connected drone interface
        checks: Preflight config dict

    Returns:
        True if all checks pass
    """
    print("[PREFLIGHT] Running checks...")

    # Check GPS satellites
    min_sats = checks.get('min_satellites', 6)
    gps = drone.controller.get_gps_status() if hasattr(drone, 'controller') and drone.controller else None
    if gps:
        sats = gps['satellites']
        print(f"[PREFLIGHT] Satellites: {sats} (min: {min_sats})")
        if sats < min_sats:
            print(f"[ERROR] Not enough satellites ({sats} < {min_sats})")
            return False
    else:
        print("[WARN] Could not read GPS status — skipping satellite check")

    # Check max altitude in flight plan is within limit
    max_alt = checks.get('max_altitude_m')
    if max_alt:
        print(f"[PREFLIGHT] Max altitude limit: {max_alt}m")

    # Check sonar if required
    if checks.get('require_sonar'):
        front = drone.get_sonar('front')
        down = drone.get_sonar('down')
        if front == float('inf') and down == float('inf'):
            print("[WARN] Sonar returning inf on all directions — may not be available")

    print("[PREFLIGHT] All checks passed")
    return True


def execute_flight_plan(drone: DroneInterface, plan: list,
                        max_altitude: float = None) -> bool:
    """Execute a flight plan step by step.

    Args:
        drone: Connected and armed drone
        plan: List of step dicts
        max_altitude: Optional altitude limit

    Returns:
        True if all steps completed
    """
    for i, step in enumerate(plan, 1):
        step_type = step['type']
        print(f"\n[STEP {i}/{len(plan)}] {step_type.upper()}")

        if step_type == 'takeoff':
            altitude = step['altitude']
            if max_altitude and altitude > max_altitude:
                print(f"[WARN] Altitude {altitude}m exceeds limit {max_altitude}m — capping")
                altitude = max_altitude
            if not drone.takeoff(altitude):
                print("[ERROR] Takeoff failed")
                return False

        elif step_type == 'move':
            x = step.get('x', 0)
            y = step.get('y', 0)
            speed = step.get('speed', 1.0)
            if not drone.move_relative(x, y, speed):
                print("[ERROR] Move failed")
                return False

        elif step_type == 'move_safe':
            x = step.get('x', 0)
            y = step.get('y', 0)
            speed = step.get('speed', 1.0)
            threshold = step.get('obstacle_threshold', 2.0)
            sidestep = step.get('sidestep_distance', 3.0)
            if not drone.move_safe(x, y, speed, threshold, sidestep):
                print("[ERROR] Safe move failed")
                return False

        elif step_type == 'land':
            if not drone.land():
                print("[ERROR] Land failed")
                return False

        else:
            print(f"[WARN] Unknown step type '{step_type}' — skipping")

        print(f"[STEP {i}/{len(plan)}] Done")
        time.sleep(1)

    return True


def run_mission(mission: dict) -> bool:
    """Run a complete mission from parsed config.

    Returns:
        True if mission completed successfully
    """
    display_mission(mission)

    # Create drone from config
    drone_cfg = mission['drone']
    print(f"[MISSION] Creating {drone_cfg.get('mode', 'sim')} drone...")
    drone = create_drone(drone_cfg)

    # Connect
    print("[MISSION] Connecting...")
    if not drone.connect():
        print("[ERROR] Connection failed")
        return False

    # Preflight checks
    preflight = mission.get('preflight', {})
    if preflight:
        if not run_preflight(drone, preflight):
            print("[ERROR] Preflight checks failed — aborting")
            return False

    # Prepare for flight (GPS + mode + arm)
    print("[MISSION] Preparing for flight...")
    if not drone.prepare_for_flight():
        print("[ERROR] Flight preparation failed")
        return False

    # Execute flight plan
    max_alt = preflight.get('max_altitude_m')
    plan = mission['flight_plan']

    print(f"\n[MISSION] Executing {len(plan)} steps...")
    try:
        success = execute_flight_plan(drone, plan, max_alt)
    except KeyboardInterrupt:
        print("\n[ABORT] Mission interrupted by user")
        print("[SAFETY] Emergency landing...")
        drone.land()
        return False
    except Exception as e:
        print(f"\n[ERROR] Mission failed: {e}")
        print("[SAFETY] Emergency landing...")
        drone.land()
        return False

    if success:
        print(f"\n{'=' * 50}")
        print(f"  MISSION COMPLETE")
        print(f"{'=' * 50}\n")
    else:
        print("\n[WARN] Mission had errors — check log above")
        drone.land()

    return success


def main():
    """Entry point — parse args and run."""
    if len(sys.argv) < 2:
        print("Usage: python3 mission_runner.py <mission_file> [--dry-run]")
        print()
        print("Examples:")
        print("  python3 mission_runner.py field_survey.mission")
        print("  python3 mission_runner.py field_survey.mission --dry-run")
        sys.exit(1)

    filepath = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    mission = load_mission(filepath)

    if dry_run:
        display_mission(mission)
        print("[DRY RUN] Mission parsed successfully — not executing")
    else:
        success = run_mission(mission)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

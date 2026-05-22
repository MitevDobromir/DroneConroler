#!/usr/bin/env python3
"""
hivemind.py - Multi-drone coordinator

The HiveMind controls multiple drones through the DroneInterface
abstraction. It can optionally designate one drone as "self" — the
drone that runs the brain.

Works identically in simulation and real life.

Usage (simulation):
    from drone_interface import SimDrone
    from hivemind import HiveMind

    hive = HiveMind()
    hive.add_drone('scout', SimDrone(instance=0, drone_name='drone1'))
    hive.add_drone('worker1', SimDrone(instance=1, drone_name='drone2'))
    hive.set_self('scout')  # optional — scout IS the hivemind

    hive.connect_all()
    hive.prepare_all()
    hive.takeoff_all(10)
    hive.execute_formation('line', spacing=5)
    hive.land_all()

Usage (real life — running ON the scout drone):
    from drone_interface import RealDrone
    from hivemind import HiveMind

    hive = HiveMind()
    hive.add_drone('scout', RealDrone('/dev/ttyACM0'))           # my own pixhawk
    hive.add_drone('worker1', RealDrone('udp:192.168.1.11:14550'))
    hive.set_self('scout')

    # Exact same mission code as simulation
    hive.connect_all()
    hive.prepare_all()
    hive.takeoff_all(10)
"""
import time
import math
import threading
from typing import Dict, List, Optional, Callable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from drone_interface import DroneInterface


class HiveMind:
    """Multi-drone coordinator with optional self-awareness.

    The hivemind holds a dictionary of named drones and provides
    methods to command them individually, in groups, or all at once.
    One drone can be designated as 'self' — the drone running the brain.
    """

    def __init__(self):
        self.drones: Dict[str, DroneInterface] = {}
        self.self_name: Optional[str] = None
        self._log_callback: Optional[Callable] = None

    # ══════════════════════════════════════════════ Setup

    def add_drone(self, name: str, drone: DroneInterface):
        """Register a drone with the hivemind.

        Args:
            name: Unique identifier (e.g. 'scout', 'worker1')
            drone: DroneInterface instance (SimDrone or RealDrone)
        """
        self.drones[name] = drone
        self._log(f"[HIVE] Registered drone '{name}' ({drone.mode}/{drone.firmware})")

    def remove_drone(self, name: str):
        """Remove a drone from the hivemind."""
        if name in self.drones:
            del self.drones[name]
            if self.self_name == name:
                self.self_name = None
            self._log(f"[HIVE] Removed drone '{name}'")

    def set_self(self, name: str):
        """Designate which drone IS the hivemind.

        This drone's sensors are used for hivemind-level decisions.
        The drone still receives commands like any other — the only
        difference is the hivemind knows it's commanding itself.

        Args:
            name: Name of the drone that is the hivemind
        """
        if name not in self.drones:
            self._log(f"[ERROR] Drone '{name}' not found")
            return
        self.self_name = name
        self._log(f"[HIVE] I am '{name}'")

    def set_log_callback(self, callback: Callable):
        """Set a callback for log messages (for GUI integration)."""
        self._log_callback = callback

    @property
    def me(self) -> Optional[DroneInterface]:
        """The drone that IS the hivemind, or None if not set."""
        if self.self_name:
            return self.drones.get(self.self_name)
        return None

    @property
    def others(self) -> Dict[str, DroneInterface]:
        """All drones except self."""
        return {n: d for n, d in self.drones.items() if n != self.self_name}

    @property
    def count(self) -> int:
        """Number of drones in the swarm."""
        return len(self.drones)

    # ══════════════════════════════════════════════ Lifecycle

    def connect_all(self) -> bool:
        """Connect to all drones. Returns True if all succeed."""
        self._log(f"[HIVE] Connecting to {self.count} drones...")
        success = True
        for name, drone in self.drones.items():
            self._log(f"[HIVE] Connecting '{name}'...")
            if not drone.connect():
                self._log(f"[ERROR] Failed to connect '{name}'")
                success = False
            else:
                self._log(f"[HIVE] '{name}' connected")
        return success

    def prepare_all(self) -> bool:
        """Prepare all drones for flight (GPS + mode + arm).

        Returns True if all succeed.
        """
        self._log(f"[HIVE] Preparing {self.count} drones for flight...")
        success = True
        for name, drone in self.drones.items():
            self._log(f"[HIVE] Preparing '{name}'...")
            if not drone.prepare_for_flight():
                self._log(f"[ERROR] Failed to prepare '{name}'")
                success = False
            else:
                self._log(f"[HIVE] '{name}' ready")
        return success

    def takeoff_all(self, altitude: float) -> bool:
        """All drones takeoff simultaneously to the same altitude."""
        self._log(f"[HIVE] All drones taking off to {altitude}m...")
        results = self._parallel(
            lambda name, drone: drone.takeoff(altitude)
        )
        return all(results.values())

    def land_all(self) -> bool:
        """All drones land simultaneously."""
        self._log(f"[HIVE] All drones landing...")
        results = self._parallel(
            lambda name, drone: drone.land()
        )
        return all(results.values())

    def emergency_land_all(self):
        """Emergency land everything — no return value, just do it."""
        self._log("[HIVE] EMERGENCY LAND ALL")
        for name, drone in self.drones.items():
            try:
                drone.land()
            except Exception:
                pass

    # ══════════════════════════════════════════════ Individual commands

    def command(self, name: str, action: str, **kwargs) -> bool:
        """Send a command to a specific drone.

        Args:
            name: Drone name
            action: 'takeoff', 'move', 'land'
            **kwargs: Action parameters (altitude, x, y, speed)

        Returns:
            True on success
        """
        drone = self.drones.get(name)
        if not drone:
            self._log(f"[ERROR] Drone '{name}' not found")
            return False

        if action == 'takeoff':
            return drone.takeoff(kwargs.get('altitude', 10))
        elif action == 'move':
            return drone.move_relative(
                kwargs.get('x', 0),
                kwargs.get('y', 0),
                kwargs.get('speed', 1.0)
            )
        elif action == 'land':
            return drone.land()
        else:
            self._log(f"[ERROR] Unknown action '{action}'")
            return False

    def command_self(self, action: str, **kwargs) -> bool:
        """Send a command to the hivemind's own drone."""
        if not self.self_name:
            self._log("[ERROR] No self drone set")
            return False
        return self.command(self.self_name, action, **kwargs)

    def command_others(self, action: str, **kwargs) -> Dict[str, bool]:
        """Send the same command to all drones except self."""
        results = {}
        for name in self.others:
            results[name] = self.command(name, action, **kwargs)
        return results

    # ══════════════════════════════════════════════ Parallel execution

    def _parallel(self, func) -> Dict[str, bool]:
        """Run a function on all drones in parallel.

        Args:
            func: callable(name, drone) -> bool

        Returns:
            dict of {name: success}
        """
        results = {}
        threads = []

        def _run(name, drone):
            try:
                results[name] = func(name, drone)
            except Exception as e:
                self._log(f"[ERROR] {name}: {e}")
                results[name] = False

        for name, drone in self.drones.items():
            t = threading.Thread(target=_run, args=(name, drone))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return results

    def move_all(self, movements: Dict[str, Dict]) -> Dict[str, bool]:
        """Move each drone to a different position simultaneously.

        Args:
            movements: {name: {'x': float, 'y': float, 'speed': float}}

        Returns:
            dict of {name: success}
        """
        self._log(f"[HIVE] Moving {len(movements)} drones simultaneously...")

        def _move(name, drone):
            m = movements.get(name)
            if not m:
                return True
            return drone.move_relative(m.get('x', 0), m.get('y', 0), m.get('speed', 1.0))

        return self._parallel(_move)

    # ══════════════════════════════════════════════ Formations

    def execute_formation(self, formation: str, spacing: float = 5.0,
                          altitude: float = 10.0) -> bool:
        """Arrange drones in a formation.

        Args:
            formation: 'line', 'v', 'square', 'circle'
            spacing: Distance between drones in meters
            altitude: Not used for movement, drones should already be airborne

        Returns:
            True if all drones reached their positions
        """
        names = list(self.drones.keys())
        n = len(names)

        if n < 2:
            self._log("[HIVE] Need at least 2 drones for a formation")
            return True

        # Calculate relative positions for each formation
        positions = {}

        if formation == 'line':
            # Spread drones along the East axis
            for i, name in enumerate(names):
                offset = (i - (n - 1) / 2) * spacing
                positions[name] = {'x': 0, 'y': offset}

        elif formation == 'v':
            # V-shape: leader at front, others spread behind
            for i, name in enumerate(names):
                if i == 0:
                    positions[name] = {'x': 0, 'y': 0}
                else:
                    side = 1 if i % 2 == 1 else -1
                    row = (i + 1) // 2
                    positions[name] = {
                        'x': -row * spacing,
                        'y': side * row * spacing
                    }

        elif formation == 'square':
            side_len = math.ceil(math.sqrt(n))
            for i, name in enumerate(names):
                row = i // side_len
                col = i % side_len
                positions[name] = {
                    'x': (row - (side_len - 1) / 2) * spacing,
                    'y': (col - (side_len - 1) / 2) * spacing
                }

        elif formation == 'circle':
            for i, name in enumerate(names):
                angle = (2 * math.pi * i) / n
                radius = spacing * n / (2 * math.pi)  # spacing = arc length
                positions[name] = {
                    'x': radius * math.cos(angle),
                    'y': radius * math.sin(angle)
                }

        else:
            self._log(f"[ERROR] Unknown formation '{formation}'")
            self._log(f"[INFO]  Available: line, v, square, circle")
            return False

        self._log(f"[HIVE] Forming '{formation}' with {spacing}m spacing...")
        for name, pos in positions.items():
            self._log(f"  {name}: N={pos['x']:.1f} E={pos['y']:.1f}")

        # Move all drones to their formation positions simultaneously
        movements = {name: {'x': pos['x'], 'y': pos['y'], 'speed': 1.0}
                     for name, pos in positions.items()}
        results = self.move_all(movements)
        return all(results.values())

    # ══════════════════════════════════════════════ Sensor queries

    def get_all_locations(self) -> Dict[str, Optional[Dict]]:
        """Get GPS location of all drones."""
        return {name: drone.get_location() for name, drone in self.drones.items()}

    def get_all_sonar(self, direction: str) -> Dict[str, float]:
        """Read a specific sonar direction from all drones.

        Args:
            direction: 'front', 'left', 'right', 'down'

        Returns:
            dict of {name: distance}
        """
        return {name: drone.get_sonar(direction) for name, drone in self.drones.items()}

    def get_distances_between(self) -> Dict[str, Dict[str, float]]:
        """Calculate distances between all drone pairs.

        Returns:
            Nested dict: distances['drone1']['drone2'] = meters
        """
        locations = self.get_all_locations()
        distances = {}

        for name1, loc1 in locations.items():
            distances[name1] = {}
            for name2, loc2 in locations.items():
                if name1 == name2 or not loc1 or not loc2:
                    distances[name1][name2] = 0.0
                    continue
                # Approximate distance using lat/lon
                dlat = (loc2['lat'] - loc1['lat']) * 111320  # meters per degree
                dlon = (loc2['lon'] - loc1['lon']) * 111320 * math.cos(
                    math.radians(loc1['lat']))
                dalt = loc2['relative_alt'] - loc1['relative_alt']
                distances[name1][name2] = math.sqrt(dlat**2 + dlon**2 + dalt**2)

        return distances

    def check_separation(self, min_distance: float = 3.0) -> List[tuple]:
        """Check if any drones are too close to each other.

        Args:
            min_distance: Minimum safe distance in meters

        Returns:
            List of (name1, name2, distance) tuples for violations
        """
        distances = self.get_distances_between()
        violations = []
        checked = set()

        for n1 in distances:
            for n2 in distances[n1]:
                if n1 == n2:
                    continue
                pair = tuple(sorted([n1, n2]))
                if pair in checked:
                    continue
                checked.add(pair)
                d = distances[n1][n2]
                if 0 < d < min_distance:
                    violations.append((n1, n2, d))

        return violations

    # ══════════════════════════════════════════════ Mission execution

    def execute_mission(self, plans: Dict[str, List[Dict]],
                        parallel: bool = True) -> Dict[str, bool]:
        """Execute flight plans for multiple drones.

        Args:
            plans: {drone_name: [{'type': 'takeoff', 'altitude': 10}, ...]}
            parallel: If True, all drones fly simultaneously.
                      If False, drones execute one at a time.

        Returns:
            dict of {name: success}
        """
        self._log(f"[HIVE] Executing mission for {len(plans)} drones "
                  f"({'parallel' if parallel else 'sequential'})...")

        def _run_plan(name, drone):
            plan = plans.get(name, [])
            for i, step in enumerate(plan, 1):
                step_type = step['type']
                self._log(f"[{name}] Step {i}/{len(plan)}: {step_type}")

                if step_type == 'takeoff':
                    if not drone.takeoff(step['altitude']):
                        return False
                elif step_type == 'move':
                    if not drone.move_relative(
                        step.get('x', 0), step.get('y', 0),
                        step.get('speed', 1.0)
                    ):
                        return False
                elif step_type == 'land':
                    if not drone.land():
                        return False

                time.sleep(0.5)
            return True

        if parallel:
            return self._parallel(_run_plan)
        else:
            results = {}
            for name, drone in self.drones.items():
                if name in plans:
                    results[name] = _run_plan(name, drone)
            return results

    # ══════════════════════════════════════════════ Monitoring

    def monitor(self, duration: float = 10.0, interval: float = 1.0,
                collision_distance: float = 3.0):
        """Monitor all drones for a duration, checking positions and separation.

        Args:
            duration: How long to monitor in seconds
            interval: Check interval in seconds
            collision_distance: Minimum safe distance in meters
        """
        self._log(f"[HIVE] Monitoring {self.count} drones for {duration}s...")
        start = time.time()

        while time.time() - start < duration:
            # Check positions
            locations = self.get_all_locations()
            for name, loc in locations.items():
                if loc:
                    self._log(f"  {name}: lat={loc['lat']:.6f} "
                              f"lon={loc['lon']:.6f} alt={loc['relative_alt']:.1f}m")

            # Check separation
            violations = self.check_separation(collision_distance)
            for n1, n2, dist in violations:
                self._log(f"  ⚠️  {n1} ↔ {n2}: {dist:.1f}m (min: {collision_distance}m)")

            time.sleep(interval)

    # ══════════════════════════════════════════════ Logging

    def _log(self, message: str):
        """Log a message to console and optional callback."""
        print(message)
        if self._log_callback:
            try:
                self._log_callback(message)
            except Exception:
                pass

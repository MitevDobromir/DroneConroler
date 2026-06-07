#!/usr/bin/env python3
"""
drone_interface.py - Abstraction layer for simulation and real drones

Provides a unified DroneInterface that the higher-level code (hivemind,
mission planner, GUI) talks to. The caller never needs to know whether
the drone is simulated or real.

Usage:
    # Simulation
    drone = SimDrone(instance=0)

    # Real drone
    drone = RealDrone(
        connection='/dev/ttyUSB0',
        firmware='ardupilot',
        baud=57600
    )

    # Both work identically
    drone.connect()
    drone.prepare_for_flight()    # GPS wait + mode + arm
    drone.takeoff(10)
    print(drone.get_sonar('front'))  # distance or inf
    drone.move_relative(5, 0)
    drone.land()
"""
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict

from flight_controller import DroneController


class DroneInterface(ABC):
    """Abstract interface for controlling a drone.

    All mission logic should use this interface so it works
    identically in simulation and real life.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the drone. Returns True on success."""
        ...

    @abstractmethod
    def prepare_for_flight(self) -> bool:
        """Wait for GPS, set guided mode, arm. Returns True when ready."""
        ...

    @abstractmethod
    def get_location(self) -> Optional[Dict]:
        """Get current GPS location (lat, lon, alt, relative_alt)."""
        ...

    @abstractmethod
    def get_sonar(self, direction: str) -> float:
        """Read sonar distance for given direction.

        Args:
            direction: 'front', 'left', 'right', or 'down'

        Returns:
            Distance in meters, or float('inf') if no obstacle detected.
        """
        ...

    @abstractmethod
    def takeoff(self, altitude: float) -> bool:
        """Takeoff to specified altitude in meters."""
        ...

    @abstractmethod
    def move_relative(self, x: float, y: float, speed: float = 1.0) -> bool:
        """Move relative to current position in world NED frame.

        Args:
            x: North offset in meters (positive = North)
            y: East offset in meters (positive = East)
            speed: Movement speed hint in m/s
        """
        ...

    @abstractmethod
    def land(self) -> bool:
        """Land the drone."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the drone is currently connected."""
        ...

    @property
    @abstractmethod
    def firmware(self) -> str:
        """Firmware type: 'ardupilot' or 'px4'."""
        ...

    @property
    @abstractmethod
    def mode(self) -> str:
        """Current operational mode: 'sim' or 'real'."""
        ...

    # ─────────────────────────────────── Obstacle avoidance (concrete)
    # These are built on top of the abstract methods above, so they
    # work automatically for both SimDrone and RealDrone.

    def move_safe(self, x: float, y: float, speed: float = 1.0,
                  obstacle_threshold: float = 2.0,
                  sidestep_distance: float = 3.0) -> bool:
        """Move relative with obstacle avoidance.

        Uses a Bug-algorithm approach:
        1. Start moving toward target
        2. If front sonar detects obstacle within threshold:
           a. Stop
           b. Check left and right sonar
           c. Sidestep toward the clearer side
           d. Move forward past the obstacle
           e. Sidestep back to the original line
           f. Continue toward target
        3. Repeat until target reached

        Args:
            x: North offset in meters
            y: East offset in meters
            speed: Movement speed hint in m/s
            obstacle_threshold: Stop when obstacle closer than this (meters)
            sidestep_distance: How far to sidestep around obstacle (meters)

        Returns:
            True if target reached (possibly via detour)
        """
        import math

        total_distance = math.sqrt(x**2 + y**2)
        if total_distance < 0.1:
            return True

        print(f"[MOVE_SAFE] Target: N={x:.1f} E={y:.1f} ({total_distance:.1f}m)")
        print(f"[MOVE_SAFE] Obstacle threshold: {obstacle_threshold}m")

        # Normalize direction vector
        dir_x = x / total_distance
        dir_y = y / total_distance

        # Perpendicular vector for sidestepping (rotate 90° clockwise)
        perp_x = dir_y
        perp_y = -dir_x

        remaining_x = x
        remaining_y = y
        max_avoidances = 5
        avoidance_count = 0

        while math.sqrt(remaining_x**2 + remaining_y**2) > 1.0:
            # Check front sonar before moving
            front_dist = self.get_sonar('front')
            remaining_dist = math.sqrt(remaining_x**2 + remaining_y**2)

            if front_dist < obstacle_threshold and avoidance_count < max_avoidances:
                avoidance_count += 1
                print(f"[AVOID] Obstacle detected at {front_dist:.1f}m — avoidance #{avoidance_count}")

                # Check sides
                left_dist = self.get_sonar('left')
                right_dist = self.get_sonar('right')
                print(f"[AVOID] Left: {left_dist:.1f}m  Right: {right_dist:.1f}m")

                # Pick the clearer side
                if left_dist >= right_dist:
                    side_name = "left"
                    step_x = -perp_x * sidestep_distance
                    step_y = -perp_y * sidestep_distance
                else:
                    side_name = "right"
                    step_x = perp_x * sidestep_distance
                    step_y = perp_y * sidestep_distance

                print(f"[AVOID] Sidestepping {side_name} by {sidestep_distance}m...")

                # Step 1: Sidestep away from obstacle
                if not self.move_relative(step_x, step_y, speed):
                    print("[AVOID] Sidestep failed")
                    return False

                # Step 2: Move forward past the obstacle
                forward_dist = obstacle_threshold + 2.0
                fwd_x = dir_x * forward_dist
                fwd_y = dir_y * forward_dist
                print(f"[AVOID] Moving forward {forward_dist:.1f}m to clear obstacle...")

                if not self.move_relative(fwd_x, fwd_y, speed):
                    print("[AVOID] Forward pass failed")
                    return False

                # Step 3: Sidestep back to original line
                print(f"[AVOID] Returning to original path...")
                if not self.move_relative(-step_x, -step_y, speed):
                    print("[AVOID] Return sidestep failed")
                    return False

                # Update remaining distance
                remaining_x -= fwd_x
                remaining_y -= fwd_y
                print(f"[AVOID] Avoidance complete — remaining: "
                      f"N={remaining_x:.1f} E={remaining_y:.1f}")

            else:
                # Path is clear — move remaining distance
                # Take steps of up to 5m to keep checking sonar frequently
                step_size = min(5.0, math.sqrt(remaining_x**2 + remaining_y**2))
                fraction = step_size / math.sqrt(remaining_x**2 + remaining_y**2)
                step_x = remaining_x * fraction
                step_y = remaining_y * fraction

                if not self.move_relative(step_x, step_y, speed):
                    print("[MOVE_SAFE] Move step failed")
                    return False

                remaining_x -= step_x
                remaining_y -= step_y

        print(f"[MOVE_SAFE] Target reached ({avoidance_count} avoidance(s))")
        return True


# ═══════════════════════════════════════════════════════════════════════════
#  Simulation drone
# ═══════════════════════════════════════════════════════════════════════════

class SimDrone(DroneInterface):
    """Simulated drone: MAVLink to SITL + Gazebo topics for sensors.

    Args:
        instance: SITL instance number (0, 1, 2...).
                  Determines port: UDP 14550 + (instance * 10)
        drone_name: Name used when spawning in Gazebo (for sensor topics).
        fw: Firmware type ('ardupilot' or 'px4').
    """

    def __init__(self, instance: int = 0, drone_name: str = 'drone1',
                 fw: str = 'ardupilot'):
        self._instance = instance
        self._drone_name = drone_name
        self._firmware = fw
        self._controller: Optional[DroneController] = None
        self._port = 14550 + (instance * 10)

        # Gazebo topic prefix for this drone's sensors
        self._sonar_prefix = f'/drone/sonar'
        if instance > 0:
            self._sonar_prefix = f'/drone{instance}/sonar'

    def connect(self) -> bool:
        try:
            self._controller = DroneController(
                connection_string=f'udp:127.0.0.1:{self._port}',
                firmware=self._firmware
            )
            return True
        except Exception as e:
            print(f"[ERROR] SimDrone connect failed: {e}")
            return False

    def prepare_for_flight(self) -> bool:
        if not self._controller:
            return False
        if not self._controller.wait_for_gps():
            return False
        if not self._controller.set_mode('guided'):
            return False
        if not self._controller.arm():
            return False
        return True

    def get_location(self) -> Optional[Dict]:
        if not self._controller:
            return None
        return self._controller.get_location()

    def get_sonar(self, direction: str) -> float:
        """Read sonar from Gazebo topic via subprocess.

        Args:
            direction: 'front', 'left', 'right', or 'down'

        Returns:
            Distance in meters, or inf if no obstacle / read failure.
        """
        topic = f'{self._sonar_prefix}/{direction}'
        try:
            result = subprocess.run(
                ['gz', 'topic', '-e', '-t', topic, '-n', '1'],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if stripped.startswith('ranges:'):
                    value = stripped.split(':')[1].strip()
                    return float(value)
        except (subprocess.TimeoutExpired, ValueError, Exception):
            pass
        return float('inf')

    def takeoff(self, altitude: float) -> bool:
        if not self._controller:
            return False
        return self._controller.takeoff(altitude)

    def move_relative(self, x: float, y: float, speed: float = 1.0) -> bool:
        if not self._controller:
            return False
        return self._controller.move_relative(x, y, speed)

    def land(self) -> bool:
        if not self._controller:
            return False
        self._controller.land()
        return True

    @property
    def is_connected(self) -> bool:
        return self._controller is not None

    @property
    def firmware(self) -> str:
        return self._firmware

    @property
    def mode(self) -> str:
        return 'sim'

    @property
    def instance(self) -> int:
        return self._instance

    @property
    def controller(self) -> Optional[DroneController]:
        """Direct access to DroneController (for advanced usage)."""
        return self._controller


# ═══════════════════════════════════════════════════════════════════════════
#  Real drone
# ═══════════════════════════════════════════════════════════════════════════

class RealDrone(DroneInterface):
    """Real hardware drone: MAVLink over serial/network.

    Sensor reading depends on your hardware setup. Override get_sonar()
    for your specific sensor (serial, I2C, ROS2 topic, etc.).

    Args:
        connection: MAVLink connection string
            USB:   '/dev/ttyACM0' or '/dev/ttyUSB0'
            WiFi:  'udp:192.168.1.100:14550'
            Radio: '/dev/ttyUSB0' (with baud=57600)
        fw: Firmware type ('ardupilot' or 'px4')
        baud: Baud rate for serial connections
        sonar_reader: Optional callable(direction) -> float for custom
                      sensor reading. If None, get_sonar returns inf.
    """

    def __init__(self, connection: str, fw: str = 'ardupilot',
                 baud: int = 57600, sonar_reader=None):
        self._connection = connection
        self._firmware = fw
        self._baud = baud
        self._controller: Optional[DroneController] = None
        self._sonar_reader = sonar_reader

    def connect(self) -> bool:
        try:
            self._controller = DroneController(
                connection_string=self._connection,
                firmware=self._firmware,
                baud=self._baud
            )
            return True
        except Exception as e:
            print(f"[ERROR] RealDrone connect failed: {e}")
            return False

    def prepare_for_flight(self) -> bool:
        if not self._controller:
            return False
        if not self._controller.wait_for_gps():
            return False
        if not self._controller.set_mode('guided'):
            return False
        if not self._controller.arm():
            return False
        return True

    def get_location(self) -> Optional[Dict]:
        if not self._controller:
            return None
        return self._controller.get_location()

    def get_sonar(self, direction: str) -> float:
        """Read sonar from real hardware.

        If a sonar_reader callable was provided, use it.
        Otherwise returns inf (no sensor configured).

        To connect real sensors, provide a sonar_reader function:
            def my_sonar(direction):
                # Read from serial, I2C, ROS2 topic, etc.
                return distance_in_meters

            drone = RealDrone('/dev/ttyUSB0', sonar_reader=my_sonar)
        """
        if self._sonar_reader:
            try:
                return self._sonar_reader(direction)
            except Exception as e:
                print(f"[WARN] Sonar read error ({direction}): {e}")
        return float('inf')

    def takeoff(self, altitude: float) -> bool:
        if not self._controller:
            return False
        return self._controller.takeoff(altitude)

    def move_relative(self, x: float, y: float, speed: float = 1.0) -> bool:
        if not self._controller:
            return False
        return self._controller.move_relative(x, y, speed)

    def land(self) -> bool:
        if not self._controller:
            return False
        self._controller.land()
        return True

    @property
    def is_connected(self) -> bool:
        return self._controller is not None

    @property
    def firmware(self) -> str:
        return self._firmware

    @property
    def mode(self) -> str:
        return 'real'

    @property
    def controller(self) -> Optional[DroneController]:
        """Direct access to DroneController (for advanced usage)."""
        return self._controller


# ═══════════════════════════════════════════════════════════════════════════
#  Factory — create drones from config dict
# ═══════════════════════════════════════════════════════════════════════════

def create_drone(config: Dict) -> DroneInterface:
    """Create a drone from a configuration dictionary.

    Simulation config:
        {
            "mode": "sim",
            "firmware": "ardupilot",
            "instance": 0,
            "drone_name": "drone1"
        }

    Real config:
        {
            "mode": "real",
            "firmware": "ardupilot",
            "connection": "/dev/ttyUSB0",
            "baud": 57600
        }

    Returns:
        DroneInterface instance (SimDrone or RealDrone)
    """
    mode = config.get('mode', 'sim')
    fw = config.get('firmware', 'ardupilot')

    if mode == 'sim':
        return SimDrone(
            instance=config.get('instance', 0),
            drone_name=config.get('drone_name', 'drone1'),
            fw=fw
        )
    elif mode == 'real':
        return RealDrone(
            connection=config['connection'],
            fw=fw,
            baud=config.get('baud', 57600)
        )
    else:
        raise ValueError(f"Unknown mode '{mode}'. Use 'sim' or 'real'.")

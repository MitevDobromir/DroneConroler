#!/usr/bin/env python3
"""
flight_controller.py - Reusable drone control abstraction

Uses pymavlink to communicate with ArduPilot over MAVLink.
Movement commands use world-frame (NED) position targets with
feedback loops for precision.
"""
import time
import math
from pymavlink import mavutil


class DroneController:
    def __init__(self, connection_string='udp:127.0.0.1:14550'):
        """Initialize connection to drone"""
        print(f"[CONNECT] Connecting to drone at {connection_string}...")
        self.master = mavutil.mavlink_connection(connection_string)
        self.master.wait_heartbeat()
        print("[SUCCESS] Heartbeat received from drone")

    def get_location(self):
        """Get current GPS location

        Returns:
            dict with lat, lon, alt, relative_alt or None if unavailable
        """
        msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)
        if msg:
            return {
                'lat': msg.lat / 1e7,
                'lon': msg.lon / 1e7,
                'alt': msg.alt / 1000.0,
                'relative_alt': msg.relative_alt / 1000.0
            }
        return None

    def _get_local_position(self):
        """Get current local NED position

        Returns:
            dict with x, y, z (NED meters) or None
        """
        msg = self.master.recv_match(type='LOCAL_POSITION_NED', blocking=True, timeout=2)
        if msg:
            return {'x': msg.x, 'y': msg.y, 'z': msg.z}
        return None

    def get_gps_status(self):
        """Get GPS fix status

        Returns:
            dict with fix_type and satellites, or None if unavailable
        """
        msg = self.master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=1)
        if msg:
            return {
                'fix_type': msg.fix_type,
                'satellites': msg.satellites_visible
            }
        return None

    def wait_for_gps(self, timeout=60):
        """Wait for GPS lock"""
        print("[GPS] Waiting for GPS lock...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            msg = self.master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=1)
            if msg:
                fix_type = msg.fix_type
                satellites = msg.satellites_visible
                print(f"[GPS] Fix type={fix_type}, Satellites={satellites}")

                if fix_type >= 3 and satellites >= 6:
                    print("[SUCCESS] GPS lock acquired!")
                    return True

        print("[ERROR] GPS lock timeout")
        return False

    def set_mode(self, mode):
        """Set flight mode"""
        print(f"[MODE] Setting mode to {mode}...")

        mode_mapping = {
            'STABILIZE': 0,
            'GUIDED': 4,
            'LAND': 9,
            'RTL': 6,
            'LOITER': 5
        }

        if mode not in mode_mapping:
            print(f"[ERROR] Unknown mode: {mode}")
            return False

        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_mapping[mode]
        )

        time.sleep(2)
        print(f"[SUCCESS] Mode set to {mode}")
        return True

    def arm(self, retries=5, retry_delay=5):
        """Arm the drone, retrying on failure

        Args:
            retries: Number of attempts (default 5)
            retry_delay: Seconds between retries (default 5)

        Returns:
            True if armed successfully
        """
        for attempt in range(1, retries + 1):
            print(f"[ARM] Arming throttle (attempt {attempt}/{retries})...")

            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0,
                1, 0, 0, 0, 0, 0, 0
            )

            start_time = time.time()
            while time.time() - start_time < 10:
                msg = self.master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
                if msg:
                    if msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                        print("[SUCCESS] Armed!")
                        return True

            if attempt < retries:
                print(f"[ARM] Failed — retrying in {retry_delay}s...")
                time.sleep(retry_delay)

        print("[ERROR] Arming failed after all attempts")
        return False

    def takeoff(self, altitude):
        """Takeoff to specified altitude"""
        print(f"[TAKEOFF] Taking off to {altitude}m...")

        self.master.mav.command_long_send(
            self.master.target_system,
            self.master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
            0,
            0, 0, 0, 0, 0, 0, altitude
        )

        start_time = time.time()
        stable_count = 0
        last_alt = 0

        while time.time() - start_time < 30:
            msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)
            if msg:
                current_alt = msg.relative_alt / 1000.0
                print(f"[TAKEOFF] Altitude: {current_alt:.1f}m / {altitude}m")

                if current_alt >= altitude * 0.90:
                    print(f"[SUCCESS] Reached target altitude!")
                    return True

                if abs(current_alt - last_alt) < 0.1:
                    stable_count += 1
                    if stable_count >= 3 and current_alt >= altitude * 0.85:
                        print(f"[SUCCESS] Altitude stabilized at {current_alt:.1f}m")
                        return True
                else:
                    stable_count = 0

                last_alt = current_alt
            time.sleep(1)

        print("[ERROR] Takeoff timeout")
        return False

    def move_forward(self, distance, speed=1.0):
        """Move forward by specified distance (world-frame North)

        Args:
            distance: Distance in meters
            speed: Movement speed in m/s

        Returns:
            True on success
        """
        return self.move_relative(distance, 0, speed)

    def move_relative(self, x, y, speed=1.0):
        """Move relative to current position in world frame (NED)

        Uses position targets with a feedback loop for precision.
        The drone's autopilot handles path following internally.

        Args:
            x: North/South offset in meters (positive = North)
            y: East/West offset in meters (positive = East)
            speed: Movement speed in m/s (not directly controlled;
                   ArduPilot uses its own speed parameters)

        Returns:
            True on success
        """
        distance = math.sqrt(x**2 + y**2)
        if distance < 0.1:
            print("[MOVE] Distance too small, skipping")
            return True

        # Get current local NED position
        current = self._get_local_position()
        if not current:
            print("[ERROR] Could not get current position")
            return False

        # Compute target in world NED frame
        target_x = current['x'] + x    # North
        target_y = current['y'] + y    # East
        target_z = current['z']        # Keep current altitude (NED: negative = up)

        print(f"[MOVE] Current: N={current['x']:.1f} E={current['y']:.1f}")
        print(f"[MOVE] Target:  N={target_x:.1f} E={target_y:.1f} ({distance:.1f}m)")

        # Send position target in LOCAL_NED frame
        # type_mask: ignore velocity, acceleration, yaw, yaw_rate
        # Bits: 0b0000_1111_1111_1000 = 0x0FF8
        #   bit 0 (x):     0 = use
        #   bit 1 (y):     0 = use
        #   bit 2 (z):     0 = use
        #   bits 3-10:     1 = ignore (velocity, accel, yaw, yaw_rate)
        type_mask = 0b0000111111111000

        self.master.mav.send(
            mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
                10,                                        # time_boot_ms
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,       # World frame
                type_mask,
                target_x, target_y, target_z,              # Position
                0, 0, 0,                                   # Velocity (ignored)
                0, 0, 0,                                   # Acceleration (ignored)
                0, 0                                       # Yaw, yaw_rate (ignored)
            )
        )

        # Wait until drone reaches target (with feedback)
        tolerance = 1.0  # meters
        timeout = max(distance / speed * 3, 15)  # generous timeout
        start_time = time.time()
        last_print = 0

        while time.time() - start_time < timeout:
            pos = self._get_local_position()
            if pos:
                dx = target_x - pos['x']
                dy = target_y - pos['y']
                remaining = math.sqrt(dx**2 + dy**2)

                # Print progress every 2 seconds
                now = time.time()
                if now - last_print >= 2:
                    print(f"[MOVE] Remaining: {remaining:.1f}m")
                    last_print = now

                if remaining < tolerance:
                    print(f"[SUCCESS] Reached target (error: {remaining:.2f}m)")
                    return True

            # Re-send target periodically to keep autopilot tracking
            self.master.mav.send(
                mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
                    10,
                    self.master.target_system,
                    self.master.target_component,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                    type_mask,
                    target_x, target_y, target_z,
                    0, 0, 0,
                    0, 0, 0,
                    0, 0
                )
            )
            time.sleep(0.5)

        print(f"[ERROR] Move timeout after {timeout:.0f}s")
        return False

    def land(self):
        """Land the drone"""
        print("[LAND] Landing...")
        self.set_mode('LAND')

        while True:
            msg = self.master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
            if msg:
                if not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
                    print("[SUCCESS] Landed and disarmed!")
                    return True
            time.sleep(1)
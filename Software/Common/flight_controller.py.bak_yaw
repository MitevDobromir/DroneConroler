#!/usr/bin/env python3
"""
flight_controller.py - MAVLink drone control abstraction

Supports both ArduPilot and PX4 firmwares. All movement commands use
world-frame (NED) position targets with feedback loops for precision.

Usage:
    # ArduPilot (default)
    drone = DroneController('udp:127.0.0.1:14550')

    # PX4
    drone = DroneController('udp:127.0.0.1:14550', firmware='px4')

    # Real drone over serial
    drone = DroneController('/dev/ttyUSB0', baud=57600)
"""
import time
import math
from pymavlink import mavutil


class DroneController:

    # Mode mappings per firmware
    MODES = {
        'ardupilot': {
            'STABILIZE': 0,
            'GUIDED': 4,
            'LAND': 9,
            'RTL': 6,
            'LOITER': 5,
        },
        'px4': {
            'MANUAL': 1,
            'OFFBOARD': 6,
            'LAND': 4,
            'RTL': 5,
            'HOLD': 3,
        },
    }

    # Map generic names to firmware-specific names
    GENERIC_MODES = {
        'ardupilot': {
            'guided': 'GUIDED',
            'land': 'LAND',
            'rtl': 'RTL',
            'loiter': 'LOITER',
            'stabilize': 'STABILIZE',
        },
        'px4': {
            'guided': 'OFFBOARD',
            'land': 'LAND',
            'rtl': 'RTL',
            'loiter': 'HOLD',
            'stabilize': 'MANUAL',
        },
    }

    def __init__(self, connection_string='udp:127.0.0.1:14550',
                 firmware='ardupilot', baud=57600):
        """Initialize connection to drone

        Args:
            connection_string: MAVLink connection URI
                Simulation:  'udp:127.0.0.1:14550'
                USB serial:  '/dev/ttyACM0' or '/dev/ttyUSB0'
                WiFi/radio:  'udp:192.168.1.100:14550'
                TCP:         'tcp:127.0.0.1:5760'
            firmware: 'ardupilot' or 'px4'
            baud: Baud rate for serial connections (default 57600)
        """
        self.firmware = firmware.lower()
        if self.firmware not in self.MODES:
            raise ValueError(f"Unknown firmware '{firmware}'. Use 'ardupilot' or 'px4'.")

        self.mode_map = self.MODES[self.firmware]
        self.generic_map = self.GENERIC_MODES[self.firmware]

        print(f"[CONNECT] Connecting to {firmware} drone at {connection_string}...")

        # Serial connections need baud rate
        if connection_string.startswith('/dev/'):
            self.master = mavutil.mavlink_connection(connection_string, baud=baud)
        else:
            self.master = mavutil.mavlink_connection(connection_string)

        self.master.wait_heartbeat()
        print(f"[SUCCESS] Heartbeat received (firmware: {firmware})")

    def get_location(self):
        """Get current GPS location

        Returns:
            dict with lat, lon, alt, relative_alt or None
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
            dict with fix_type and satellites, or None
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

    def wait_ready(self, timeout=90):
        """Wait for the autopilot to be fully ready to arm.

        Tries to detect EKF convergence via STATUSTEXT messages.
        If MAVProxy is consuming the messages (common), falls back
        to a fixed wait period.

        Args:
            timeout: Maximum seconds to wait (default 90)

        Returns:
            True when ready, False on timeout (still safe to proceed)
        """
        print("[READY] Waiting for autopilot to initialize...")
        start_time = time.time()

        ekf_origin_set = False
        ekf_using_gps = False
        ardupilot_ready = False
        seen_any_status = False

        while time.time() - start_time < timeout:
            msg = self.master.recv_match(
                type=['STATUSTEXT', 'HEARTBEAT'], blocking=True, timeout=1)

            if msg and msg.get_type() == 'STATUSTEXT':
                text = msg.text.strip()
                if text:
                    seen_any_status = True
                    print(f"[READY] {text}")

                    if 'ArduPilot Ready' in text:
                        ardupilot_ready = True
                    if 'origin set' in text:
                        ekf_origin_set = True
                    if 'is using GPS' in text:
                        ekf_using_gps = True

                    # Best case: EKF fully converged
                    if ekf_origin_set and ekf_using_gps:
                        print("[SUCCESS] EKF converged — ready to arm!")
                        time.sleep(2)
                        return True

            elapsed = time.time() - start_time

            # If we got ArduPilot Ready + 30s elapsed, good enough
            if elapsed > 30 and ardupilot_ready:
                print("[SUCCESS] Autopilot ready (30s elapsed)")
                time.sleep(2)
                return True

            # If we haven't seen ANY STATUSTEXT after 15 seconds,
            # MAVProxy is consuming them — fall back to fixed wait
            if elapsed > 15 and not seen_any_status:
                wait_time = 30
                print(f"[READY] No status messages received (MAVProxy consuming them)")
                print(f"[READY] Falling back to {wait_time}s fixed wait...")
                time.sleep(wait_time)
                return True

        # Timeout — add safety delay
        print("[READY] Timeout — adding 30s safety delay for EKF...")
        time.sleep(30)
        return True

    def set_mode(self, mode):
        """Set flight mode

        Accepts firmware-specific names (GUIDED, OFFBOARD) or
        generic names (guided, land, rtl, loiter, stabilize).
        Generic names are mapped to the correct firmware mode.

        Args:
            mode: Mode name (case-insensitive)

        Returns:
            True on success
        """
        # Try generic mapping first
        mode_lower = mode.lower()
        if mode_lower in self.generic_map:
            fw_mode = self.generic_map[mode_lower]
        else:
            fw_mode = mode.upper()

        if fw_mode not in self.mode_map:
            print(f"[ERROR] Unknown mode '{mode}' for {self.firmware}")
            print(f"[INFO]  Available: {list(self.mode_map.keys())}")
            print(f"[INFO]  Generic:   {list(self.generic_map.keys())}")
            return False

        mode_id = self.mode_map[fw_mode]
        print(f"[MODE] Setting mode to {fw_mode} (id={mode_id})...")

        # PX4 Offboard mode requires active position streaming
        # before the mode switch will be accepted
        if self.firmware == 'px4' and fw_mode == 'OFFBOARD':
            self._px4_pre_offboard()

        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )

        time.sleep(2)
        print(f"[SUCCESS] Mode set to {fw_mode}")
        return True

    def _px4_pre_offboard(self):
        """PX4 requires position target stream before entering Offboard mode"""
        pos = self._get_local_position()
        if not pos:
            return

        type_mask = 0b0000111111111000
        for _ in range(10):
            self.master.mav.send(
                mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
                    10, self.master.target_system, self.master.target_component,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED, type_mask,
                    pos['x'], pos['y'], pos['z'],
                    0, 0, 0, 0, 0, 0, 0, 0
                )
            )
            time.sleep(0.1)

    def arm(self, retries=10, retry_delay=5):
        """Arm the drone, retrying on failure

        Args:
            retries: Number of attempts (default 10)
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

    def takeoff(self, altitude, timeout=60):
        """Takeoff to specified altitude

        Args:
            altitude: Target altitude in meters
            timeout: Maximum seconds to wait (default 60)
        """
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

        while time.time() - start_time < timeout:
            msg = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=True, timeout=1)
            if msg:
                current_alt = msg.relative_alt / 1000.0
                print(f"[TAKEOFF] Altitude: {current_alt:.2f}m / {altitude}m")

                if current_alt >= altitude * 0.80:
                    print(f"[SUCCESS] Reached target altitude!")
                    return True

                if abs(current_alt - last_alt) < 0.15:
                    stable_count += 1
                    if stable_count >= 3 and current_alt >= altitude * 0.75:
                        print(f"[SUCCESS] Altitude stabilized at {current_alt:.1f}m")
                        return True
                else:
                    stable_count = 0

                last_alt = current_alt
            time.sleep(1)

        print("[ERROR] Takeoff timeout")
        return False

    def move_forward(self, distance, speed=1.0):
        """Move forward by specified distance (world-frame North)"""
        return self.move_relative(distance, 0, speed)

    def move_relative(self, x, y, speed=1.0):
        """Move relative to current position in world frame (NED)

        Uses position targets with a feedback loop for precision.

        Args:
            x: North/South offset in meters (positive = North)
            y: East/West offset in meters (positive = East)
            speed: Used for timeout calculation

        Returns:
            True on success
        """
        distance = math.sqrt(x**2 + y**2)
        if distance < 0.1:
            print("[MOVE] Distance too small, skipping")
            return True

        current = self._get_local_position()
        if not current:
            print("[ERROR] Could not get current position")
            return False

        target_x = current['x'] + x
        target_y = current['y'] + y
        target_z = current['z']

        print(f"[MOVE] Current: N={current['x']:.1f} E={current['y']:.1f}")
        print(f"[MOVE] Target:  N={target_x:.1f} E={target_y:.1f} ({distance:.1f}m)")

        type_mask = 0b0000111111111000

        self.master.mav.send(
            mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
                10, self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED, type_mask,
                target_x, target_y, target_z,
                0, 0, 0, 0, 0, 0, 0, 0
            )
        )

        tolerance = 1.0
        timeout = max(distance / speed * 5, 30)
        start_time = time.time()
        last_print = 0

        while time.time() - start_time < timeout:
            pos = self._get_local_position()
            if pos:
                dx = target_x - pos['x']
                dy = target_y - pos['y']
                remaining = math.sqrt(dx**2 + dy**2)

                now = time.time()
                if now - last_print >= 2:
                    print(f"[MOVE] Remaining: {remaining:.1f}m")
                    last_print = now

                if remaining < tolerance:
                    print(f"[SUCCESS] Reached target (error: {remaining:.2f}m)")
                    return True

            self.master.mav.send(
                mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
                    10, self.master.target_system, self.master.target_component,
                    mavutil.mavlink.MAV_FRAME_LOCAL_NED, type_mask,
                    target_x, target_y, target_z,
                    0, 0, 0, 0, 0, 0, 0, 0
                )
            )
            time.sleep(0.5)

        print(f"[ERROR] Move timeout after {timeout:.0f}s")
        return False

    def land(self):
        """Land the drone"""
        print("[LAND] Landing...")
        self.set_mode('land')

        while True:
            msg = self.master.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
            if msg:
                if not (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED):
                    print("[SUCCESS] Landed and disarmed!")
                    return True
            time.sleep(1)
#!/usr/bin/env python3
"""
flight_controller.py - Reusable drone control abstraction
"""
import time
from pymavlink import mavutil

class DroneController:
    def __init__(self, connection_string='udp:127.0.0.1:14550'):
        """Initialize connection to drone"""
        print(f"[CONNECT] Connecting to drone at {connection_string}...")
        self.master = mavutil.mavlink_connection(connection_string)
        self.master.wait_heartbeat()
        print("[SUCCESS] Heartbeat received from drone")
        
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
    
    def arm(self):
        """Arm the drone"""
        print("[ARM] Arming throttle...")
        
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
        
        print("[ERROR] Arming failed")
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
                
                # Success if we reach 90% of target altitude
                if current_alt >= altitude * 0.90:
                    print(f"[SUCCESS] Reached target altitude!")
                    return True
                
                # Also succeed if altitude is stable (not changing much)
                if abs(current_alt - last_alt) < 0.1:
                    stable_count += 1
                    if stable_count >= 3 and current_alt >= altitude * 0.85:
                        print(f"[SUCCESS] Altitude stabilized at {current_alt:.1f}m (close enough)")
                        return True
                else:
                    stable_count = 0
                
                last_alt = current_alt
            time.sleep(1)
        
        print("[ERROR] Takeoff timeout")
        return False
    
    def move_forward(self, distance, speed=1.0):
        """Move forward by specified distance"""
        print(f"[MOVE] Moving {distance}m forward at {speed}m/s...")
        
        self.master.mav.send(
            mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
                10,
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
                0b0000111111000111,
                0, 0, 0,
                speed, 0, 0,
                0, 0, 0,
                0, 0
            )
        )
        
        move_time = distance / speed
        print(f"[MOVE] Moving for {move_time:.1f} seconds...")
        time.sleep(move_time)
        
        print("[MOVE] Stopping...")
        self.master.mav.send(
            mavutil.mavlink.MAVLink_set_position_target_local_ned_message(
                10,
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_BODY_OFFSET_NED,
                0b0000111111000111,
                0, 0, 0,
                0, 0, 0,
                0, 0, 0,
                0, 0
            )
        )
        
        print("[SUCCESS] Movement complete")
        return True
    
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
#!/usr/bin/env python3
"""
auto_flight.py - Automated flight mission
"""
import sys
import os

# Add Common directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flight_controller import DroneController

def main():
    """Main flight sequence"""
    print("=" * 50)
    print("Automated Drone Flight Script")
    print("=" * 50)
    
    try:
        # Initialize drone
        drone = DroneController()
        
        # Wait for GPS
        if not drone.wait_for_gps():
            print("[ERROR] Failed to get GPS lock")
            return
        
        # Set GUIDED mode
        if not drone.set_mode('GUIDED'):
            return
        
        # Arm
        if not drone.arm():
            return
        
        # Takeoff
        if not drone.takeoff(5):
            return
        
        # Move forward 5 meters
        if not drone.move_forward(5, speed=1.0):
            return
        
        # Land
        drone.land()
        
        print("\n" + "=" * 50)
        print("[SUCCESS] Flight sequence completed successfully!")
        print("=" * 50)
        
    except KeyboardInterrupt:
        print("\n[WARNING] Flight interrupted by user")
        if 'drone' in locals():
            drone.land()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        if 'drone' in locals():
            drone.land()

if __name__ == "__main__":
    main()
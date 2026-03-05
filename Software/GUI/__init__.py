"""
Drone Control Center
====================

A unified GUI for drone simulation with five tabs:
- Environment: Launch Gazebo worlds
- Spawner: Spawn drone models into the simulation
- Drivers: Launch and manage flight controller drivers (SITL, custom)
- Controller: Control drones via MAVLink
- Simulations: Run pre-loaded end-to-end simulation scenarios

Usage:
    cd ~/ROS2_Tools/Software
    python3 -m GUI
"""

__version__ = "1.2.0"

# Lazy imports — main.py handles all internal wiring.
# This avoids circular import chains when the package loads.
from .main import main
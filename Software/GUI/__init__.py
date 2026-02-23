"""
Drone Control Center
====================

A unified GUI for drone simulation with four tabs:
- Environment: Launch Gazebo worlds
- Spawner: Spawn drone models into the simulation
- Drivers: Launch and manage flight controller drivers (SITL, custom)
- Controller: Control drones via MAVLink

Usage:
    cd ~/ROS2_Tools/Software
    python3 -m GUI
"""

from .global_state import GlobalState, STATE
from .theme import apply_theme, COLORS
from .environment_tab import EnvironmentTab
from .spawner_tab import SpawnerTab
from .driver_tab import DriverTab
from .controller_tab import ControllerTab
from .main import DroneControlCenter, main

__version__ = "1.1.0"
__all__ = [
    'GlobalState',
    'STATE',
    'apply_theme',
    'COLORS',
    'EnvironmentTab',
    'SpawnerTab',
    'DriverTab',
    'ControllerTab',
    'DroneControlCenter',
    'main'
]
"""
Drone Control Center
====================

A unified GUI for drone simulation with three tabs:
- Environment: Launch Gazebo worlds
- Spawner: Spawn drone models into the simulation
- Controller: Control drones via MAVLink

Usage:
    python -m drone_control_center

Or run directly:
    python drone_control_center/main.py
"""

from .global_state import GlobalState, STATE
from .environment_tab import EnvironmentTab
from .spawner_tab import SpawnerTab
from .controller_tab import ControllerTab
from .main import DroneControlCenter, main

__version__ = "1.0.0"
__all__ = [
    'GlobalState',
    'STATE',
    'EnvironmentTab',
    'SpawnerTab',
    'ControllerTab',
    'DroneControlCenter',
    'main'
]

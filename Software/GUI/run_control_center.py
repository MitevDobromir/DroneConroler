#!/usr/bin/env python3
"""
run_control_center.py - Launcher script for Drone Control Center

Place this in ~/ROS2_Tools/Software/GUI/ alongside the drone_control_center package.
"""
import sys
from pathlib import Path

# Add the GUI directory to path so we can import drone_control_center
gui_path = Path(__file__).parent
sys.path.insert(0, str(gui_path))

from drone_control_center import main

if __name__ == "__main__":
    main()

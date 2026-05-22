#!/bin/bash
# launch_env.sh - Simple Drone Environment Loader
# Usage: ./launch_env.sh [world_file]
#
# Launches Gazebo in server-only mode with EGL headless rendering, so
# GPU sensors (gpu_lidar / camera) produce data on VirtualBox/Wayland.
# No visible Gazebo window is opened. To inspect the world visually,
# switch the VM session to X11 and run `gz sim -g` in a second terminal.

# NOTE: LIBGL_ALWAYS_SOFTWARE is intentionally NOT set - see
# setup_ardupilot_env.sh for the reasoning.

# Source ROS 2 environment
source /opt/ros/jazzy/setup.bash

# Source ArduPilot environment (includes plugin paths)
source ~/ROS2_Tools/ArduPilot/setup_ardupilot_env.sh

# Tell Gazebo where to find custom models and worlds
export ROS2_TOOLS_PATH=~/ROS2_Tools
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$ROS2_TOOLS_PATH/Models
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$ROS2_TOOLS_PATH/Worlds

# Tell Gazebo where to find custom plugins
export GAZEBO_PLUGIN_PATH=$GAZEBO_PLUGIN_PATH:$ROS2_TOOLS_PATH/Software/Common

# Use provided world or default
if [ $# -eq 0 ]; then
    WORLD="plains_env.sdf"
else
    WORLD="$1"
fi

echo "Loading world: $WORLD (headless rendering - sensors active, no window)"

# Launch Gazebo server with EGL headless rendering
gz_cmd = f'gz sim -r -v4 {world_path}'
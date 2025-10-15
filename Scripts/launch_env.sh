#!/bin/bash
# launch_env.sh - Simple Drone Environment Loader
# Usage: ./launch_env.sh [world_file]

# Set software rendering for VirtualBox
export LIBGL_ALWAYS_SOFTWARE=1

# Source ROS 2 environment
source /opt/ros/jazzy/setup.bash

# Source ArduPilot environment (includes plugin paths)
source ~/ROS2_Tools/ArduPilot/setup_ardupilot_env.sh

# Get the full absolute path of your ROS2_Tools directory
export ROS2_TOOLS_PATH=~/ROS2_Tools

# ✅ Tell Gazebo where to find your custom models and worlds
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$ROS2_TOOLS_PATH/Models
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:$ROS2_TOOLS_PATH/Worlds

# ✅ Tell Gazebo where to find your custom plugins
export GAZEBO_PLUGIN_PATH=$GAZEBO_PLUGIN_PATH:$ROS2_TOOLS_PATH/Software/Common

# Use provided world or default to drone test world
if [ $# -eq 0 ]; then
    WORLD="plains_env.sdf"
else
    WORLD="$1"
fi

echo "Loading world: $WORLD"

# Launch Gazebo
ros2 launch ros_gz_sim gz_sim.launch.py gz_args:="-r -v4 $WORLD"

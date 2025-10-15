#!/bin/bash
# ArduPilot + Gazebo Environment Setup

# Source ROS2
source /opt/ros/jazzy/setup.bash

# Set Gazebo version
export GZ_VERSION=harmonic

# Software rendering for VirtualBox
export LIBGL_ALWAYS_SOFTWARE=1

# ArduPilot paths
ARDUPILOT_BASE="$HOME/ROS2_Tools/ArduPilot"
ARDUPILOT_PLUGIN_PATH="$ARDUPILOT_BASE/ardupilot_gazebo/build"

# Find ROS plugin paths
ROS_PLUGIN_PATHS="$(find /opt/ros/jazzy -name "lib" -type d 2>/dev/null | tr '\n' ':' | sed 's/:$//')"

# Set Gazebo plugin path (avoid duplicates)
export GZ_SIM_SYSTEM_PLUGIN_PATH="$ARDUPILOT_PLUGIN_PATH:$ROS_PLUGIN_PATHS:$GZ_SIM_SYSTEM_PLUGIN_PATH"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$(echo "$GZ_SIM_SYSTEM_PLUGIN_PATH" | sed 's/::/:/g' | sed 's/^://' | sed 's/:$//')"

# Set Gazebo resource paths
export GZ_SIM_RESOURCE_PATH="$ARDUPILOT_BASE/ardupilot_gazebo/models:$ARDUPILOT_BASE/ardupilot_gazebo/worlds:$GZ_SIM_RESOURCE_PATH"

# Add ArduPilot tools to PATH
export PATH="$ARDUPILOT_BASE/ardupilot/Tools/autotest:$PATH"

echo "🚁 ArduPilot + Gazebo environment loaded!"
echo "📦 Gazebo version: $GZ_VERSION"
echo "🔧 Plugin path: $GZ_SIM_SYSTEM_PLUGIN_PATH"

# Verify plugins
if [ -f "$ARDUPILOT_PLUGIN_PATH/libArduPilotPlugin.so" ]; then
    echo "✅ ArduPilot plugin found"
else
    echo "❌ ArduPilot plugin not found"
fi

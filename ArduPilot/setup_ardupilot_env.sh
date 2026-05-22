#!/bin/bash
# ArduPilot + Gazebo Environment Setup

# Source ROS2
source /opt/ros/jazzy/setup.bash

# Set Gazebo version
export GZ_VERSION=harmonic

# --- Rendering on VirtualBox (Ubuntu 24.04) ---
# VirtualBox exposes no usable Vulkan device, so Mesa's default Zink
# (OpenGL-on-Vulkan) path fails with "ZINK: failed to choose pdev" and
# the sensor render thread can't create a GL context (gpu_lidar / camera
# produce no data). Force Mesa to use the llvmpipe software renderer,
# which gives a working GL context for both the GUI and the sensor thread.
# This is CPU rendering (slower) but it is the only path that works for
# GPU-rendered sensors in this VM.
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export __GLX_VENDOR_LIBRARY_NAME=mesa
# Do NOT set LIBGL_ALWAYS_SOFTWARE - it conflicts with the above and
# corrupts EGL vendor selection on this guest.

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

echo "ArduPilot + Gazebo environment loaded"
echo "Gazebo version: $GZ_VERSION"
echo "Renderer: llvmpipe (software, VirtualBox-safe)"

# Verify plugins
if [ -f "$ARDUPILOT_PLUGIN_PATH/libArduPilotPlugin.so" ]; then
    echo "[OK] ArduPilot plugin found"
else
    echo "[ERROR] ArduPilot plugin not found"
fi
#!/bin/bash
# spawn_drone.sh - Simple drone spawner
# Usage: ./spawn_drone.sh <drone_name> <model> <x> <y> <z> [world]
# Example: ./spawn_drone.sh drone1 Cube 0 0 2
# Example: ./spawn_drone.sh drone1 cube_ardupilot 0 0 2 plains_world

# Check arguments
if [ $# -lt 5 ]; then
    echo "Usage: $0 <drone_name> <model> <x> <y> <z> [world]"
    echo ""
    echo "Examples:"
    echo "  $0 drone1 Cube 0 0 2"
    echo "  $0 drone1 cube_ardupilot 0 0 2"
    echo "  $0 drone1 Cube 0 0 2 plains_world"
    exit 1
fi

# Parameters
DRONE_NAME="$1"
MODEL_TYPE="$2"
X_POS="$3"
Y_POS="$4"
Z_POS="$5"
WORLD_NAME="${6:-plains_world}"

# Model path
MODEL_SDF="$HOME/ROS2_Tools/Models/$MODEL_TYPE.sdf"

# Check if model exists
if [ ! -f "$MODEL_SDF" ]; then
    echo "Error: Model not found at $MODEL_SDF"
    exit 1
fi

# Check if Gazebo is running
if ! pgrep -f "gz sim" > /dev/null; then
    echo "Error: Gazebo not running. Start with: ./launch_env.sh"
    exit 1
fi

echo "Spawning: $DRONE_NAME ($MODEL_TYPE) at ($X_POS, $Y_POS, $Z_POS)"

# Spawn drone
gz service -s /world/$WORLD_NAME/create \
  --reqtype gz.msgs.EntityFactory \
  --reptype gz.msgs.Boolean \
  --timeout 1000 \
  --req "sdf_filename: \"$MODEL_SDF\", name: \"$DRONE_NAME\", pose: {position: {x: $X_POS, y: $Y_POS, z: $Z_POS}}"

if [ $? -eq 0 ]; then
    echo "✓ Spawned $DRONE_NAME"
else
    echo "✗ Failed to spawn $DRONE_NAME"
    exit 1
fi
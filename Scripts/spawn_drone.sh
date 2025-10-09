#!/bin/bash

# spawn_drone.sh - Generic drone spawner for formation system
# Usage: ./spawn_drone.sh [-m model] <drone_name> <x> <y> <z> [world_name]
# Example: ./spawn_drone.sh drone_1 0 0 2
# Example: ./spawn_drone.sh -m Cube queen_drone 0 0 3

# Default values
MODEL_TYPE="Cube"
WORLD_NAME="plains_world"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--model)
            MODEL_TYPE="$2"
            shift 2
            ;;
        -w|--world)
            WORLD_NAME="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [-m model] [-w world] <drone_name> <x> <y> <z>"
            echo ""
            echo "Options:"
            echo "  -m, --model    Model type (default: Cube)"
            echo "  -w, --world    World name (default: plains_world)"
            echo "  -h, --help     Show this help"
            echo ""
            echo "Available models in Models/:"
            ls -1 "$HOME/ROS2_Tools/Models/"*.sdf 2>/dev/null | xargs -n1 basename -s .sdf || echo "  No models found"
            echo ""
            echo "Examples:"
            echo "  $0 drone_1 0 0 2"
            echo "  $0 -m Cube queen_drone 0 0 3"
            echo "  $0 -m SolidWorks worker_1 1.5 -1.5 2"
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

# Check remaining arguments
if [ $# -lt 4 ]; then
    echo "Error: Missing required arguments"
    echo "Usage: $0 [-m model] <drone_name> <x> <y> <z> [world_name]"
    echo "Use -h for help"
    exit 1
fi

# Parameters
DRONE_NAME="$1"
X_POS="$2"
Y_POS="$3"
Z_POS="$4"
WORLD_NAME="${5:-$WORLD_NAME}"

# Model path - look directly in Models folder
MODEL_SDF="$HOME/ROS2_Tools/Models/$MODEL_TYPE.sdf"

# Validate inputs
if ! [[ "$X_POS" =~ ^-?[0-9]+\.?[0-9]*$ ]]; then
    echo "Error: X position must be a number"
    exit 1
fi

if ! [[ "$Y_POS" =~ ^-?[0-9]+\.?[0-9]*$ ]]; then
    echo "Error: Y position must be a number"
    exit 1
fi

if ! [[ "$Z_POS" =~ ^-?[0-9]+\.?[0-9]*$ ]]; then
    echo "Error: Z position must be a number"
    exit 1
fi

# Check if model exists
if [ ! -f "$MODEL_SDF" ]; then
    echo "Error: Model not found at $MODEL_SDF"
    echo "Available models in Models/:"
    ls -1 "$HOME/ROS2_Tools/Models/"*.sdf 2>/dev/null | xargs -n1 basename -s .sdf || echo "  No models found"
    exit 1
fi

# Check if Gazebo is running
if ! pgrep -f "gz sim" > /dev/null; then
    echo "Error: Gazebo simulation not running"
    echo "Please start Gazebo first with: ./launch_env.sh"
    exit 1
fi

echo "Spawning drone: $DRONE_NAME"
echo "  Model: $MODEL_TYPE"
echo "  Position: $X_POS, $Y_POS, $Z_POS"
echo "  World: $WORLD_NAME"

# Spawn drone using Gazebo service
gz service -s /world/$WORLD_NAME/create \
  --reqtype gz.msgs.EntityFactory \
  --reptype gz.msgs.Boolean \
  --timeout 1000 \
  --req "sdf_filename: \"$MODEL_SDF\", name: \"$DRONE_NAME\", pose: {position: {x: $X_POS, y: $Y_POS, z: $Z_POS}}"

# Check if spawn was successful
if [ $? -eq 0 ]; then
    echo "✓ Drone '$DRONE_NAME' spawned successfully"
    echo "  ROS topics will be available at:"
    echo "    /model/$DRONE_NAME/cmd_vel"
    echo "    /model/$DRONE_NAME/pose"
    echo "    /model/$DRONE_NAME/odometry"
else
    echo "✗ Failed to spawn drone '$DRONE_NAME'"
    echo "  Check that Gazebo is running and world name is correct"
    exit 1
fi

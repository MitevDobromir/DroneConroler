# ROS2_Tools — Drone Control Center

A desktop application for running ArduPilot drone simulations in Gazebo, built on ROS2 Jazzy.

Launch environments, spawn drones, start SITL flight controllers, and run automated flight missions — all from a single GUI.

## Tech Stack

- **OS:** Ubuntu 24.04 LTS
- **Robot middleware:** ROS2 Jazzy
- **Simulator:** Gazebo Harmonic (gz-sim 8)
- **Flight controller:** ArduPilot SITL (ArduCopter)
- **MAVLink:** pymavlink + MAVProxy
- **GUI:** Python tkinter

## Quick Start

### 1. Install dependencies

```bash
cd ~/ROS2_Tools/Scripts
./install_dependencies.sh
./setup_ardupilot.sh
./build_ArduPilot.sh
```

### 2. Launch the GUI

```bash
cd ~/ROS2_Tools/Software
python3 -m GUI
```

### 3. Run a simulation

Select a `.simulation` file from the Simulations tab and click **Launch**. The system will:

1. Start Gazebo server (headless) + open GUI window
2. Spawn the drone model
3. Launch ArduCopter SITL + MAVProxy
4. Connect via MAVLink, wait for GPS, arm
5. Execute the flight plan
6. Land and clean up

## Directory Layout

```
ROS2_Tools/
├── ArduPilot/              # ArduPilot source + Gazebo plugin
├── Models/                 # Custom drone SDF models
├── Worlds/                 # Gazebo world SDF files
│   └── plains_env.sdf
├── Simulations/            # .simulation preset files
│   └── field_inspection.simulation
├── Scripts/                # Setup and utility shell scripts
├── Software/
│   ├── Common/
│   │   └── flight_controller.py   # MAVLink drone control library
│   └── GUI/                       # Drone Control Center application
│       ├── main.py
│       ├── global_state.py
│       ├── theme.py
│       ├── environment_tab.py
│       ├── spawner_tab.py
│       ├── driver_tab.py
│       ├── controller_tab.py
│       └── simulation_tab.py
└── Documentation/
```

## GUI Tabs

### Environment

Launch Gazebo world files. Scans `~/ROS2_Tools/Worlds/` for `.sdf` files. Supports image previews (add a matching `.jpg` in `Worlds/previews/`).

### Spawn Drones

Spawn drone models into a running environment. Scans both `~/ROS2_Tools/Models/` (flat `.sdf` files) and the ArduPilot Gazebo models directory (`<model>/model.sdf` folders). Configurable name, position, and world.

### Drivers

Launch and manage SITL flight controller processes. Includes built-in presets for ArduCopter, ArduPlane, and ArduRover. Supports custom driver configurations saved to JSON.

### Controller

Manual drone control via MAVLink. Connect to a running SITL, view live GPS telemetry, and build step-by-step missions (takeoff → move → land) with a visual mission builder.

### Simulations

End-to-end automated missions. Reads `.simulation` files from `~/ROS2_Tools/Simulations/` and orchestrates the full pipeline: environment → drone → SITL → MAVLink → flight plan.

## Simulation File Format

Create a `.simulation` file (JSON) in `~/ROS2_Tools/Simulations/`:

```json
{
    "name": "Field Inspection",
    "description": "Rectangular survey pattern at 15m altitude.",
    "environment": {
        "world_file": "plains_env.sdf",
        "world_name": "plains_world"
    },
    "drone": {
        "model_path": "$ARDUPILOT_GAZEBO/models/iris_with_ardupilot/model.sdf",
        "spawn_name": "iris_inspector",
        "spawn_position": [0, 0, 0.5]
    },
    "driver": {
        "binary": "$ARDUPILOT_HOME/build/sitl/bin/arducopter",
        "defaults": "default_params/copter.parm,default_params/gazebo-iris.parm",
        "working_dir": "$ARDUPILOT_HOME/Tools/autotest"
    },
    "flight_plan": [
        {"type": "takeoff", "altitude": 15},
        {"type": "move", "x": -50, "y": 0, "speed": 3.0},
        {"type": "move", "x": 0, "y": -50, "speed": 3.0},
        {"type": "move", "x": 50, "y": 0, "speed": 3.0},
        {"type": "move", "x": 0, "y": 50, "speed": 3.0},
        {"type": "land"}
    ]
}
```

**Path variables:** `$ARDUPILOT_HOME` and `$ARDUPILOT_GAZEBO` are resolved automatically.

**Flight plan step types:**

| Type | Parameters | Description |
|------|-----------|-------------|
| `takeoff` | `altitude` (m) | Takeoff to altitude in GUIDED mode |
| `move` | `x`, `y` (m), `speed` (m/s) | Move in world NED frame (x=North, y=East) |
| `land` | — | Switch to LAND mode, wait for disarm |

## Manual Workflow

If you prefer manual control instead of the Simulations tab:

```
Tab 1 (Environment):  Launch plains_env.sdf
Tab 2 (Spawn):        Spawn iris_with_ardupilot at origin
Tab 3 (Drivers):      Start ArduCopter SITL
Tab 4 (Controller):   Connect → build mission → run
```

## Flight Controller API

`Software/Common/flight_controller.py` provides a reusable Python class:

```python
from flight_controller import DroneController

drone = DroneController()          # Connect to UDP 14550
drone.wait_for_gps()               # Wait for GPS lock
drone.set_mode('GUIDED')           # Enter GUIDED mode
drone.arm()                        # Arm motors
drone.takeoff(10)                  # Climb to 10m
drone.move_relative(20, 0)         # Fly 20m North (world frame)
drone.move_relative(0, 15)         # Fly 15m East
drone.land()                       # Land and disarm
```

Movement uses `MAV_FRAME_LOCAL_NED` (world-fixed coordinates) with position feedback, so the drone follows precise paths regardless of heading changes.

## VirtualBox Notes

On Ubuntu 24.04 under VirtualBox, snap's `libpthread.so` conflicts crash both `gnome-terminal` and the Gazebo GUI. This project works around both:

- **Gazebo** runs as a headless server (`gz sim -s`), with the GUI launched as a separate crash-tolerant process (`gz sim -g`)
- **ArduCopter** is launched directly as a background process, bypassing `sim_vehicle.py` and its `gnome-terminal` dependency
- **MAVProxy** runs in daemon mode with no console window

If the Gazebo GUI window fails to open, the simulation continues running headless. All flight control works without visualization.

## Requirements

- Ubuntu 24.04
- ROS2 Jazzy (`ros-jazzy-desktop`)
- Gazebo Harmonic (`gz-harmonic`)
- ArduPilot source (cloned by setup script)
- Python packages: `pymavlink`, `mavproxy`
- Optional: `python3-pil` (Pillow) for model/world previews

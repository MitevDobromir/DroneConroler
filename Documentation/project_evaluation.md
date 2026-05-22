# Drone Control Center — Project Evaluation

**Date:** March 2026  
**Platform:** Ubuntu 24.04, VirtualBox, ROS2 Jazzy, Gazebo Harmonic, ArduPilot SITL

---

## Project Overview

A tkinter-based GUI application for controlling ArduPilot drone simulations in Gazebo. The system manages the full lifecycle: launching physics environments, spawning drone models, starting SITL flight controllers, and executing automated flight plans — all from a single desktop application.

---

## Directory Structure

```
~/ROS2_Tools/
├── ArduPilot/
│   ├── ardupilot/                    # ArduPilot source (cloned)
│   ├── ardupilot_gazebo/             # Gazebo plugin (cloned)
│   └── setup_ardupilot_env.sh        # Environment setup (generated)
├── Documentation/
│   └── todo.txt
├── Models/                           # Custom drone SDF models
├── Scripts/
│   ├── build_ArduPilot.sh            # Build Gazebo plugins
│   ├── install_dependencies.sh       # Apt + pip dependencies
│   ├── launch_env.sh                 # Manual Gazebo launcher
│   ├── setup_ardupilot.sh            # Full ArduPilot setup
│   ├── spawn_drone.sh                # Manual drone spawner
│   ├── spawn_ardu_drone.sh           # Spawn iris_with_ardupilot
│   └── launch_ardu_STIL.sh           # Manual SITL launcher
├── Simulations/
│   └── field_inspection.simulation   # Automated mission file
├── Software/
│   ├── Common/
│   │   ├── flight_controller.py      # MAVLink drone control library
│   │   └── auto_pilot.py             # Standalone flight script
│   └── GUI/
│       ├── __init__.py
│       ├── __main__.py
│       ├── main.py                   # App entry point, tab wiring
│       ├── global_state.py           # Shared state singleton
│       ├── theme.py                  # Dark theme styling
│       ├── environment_tab.py        # Tab 1: Gazebo world launcher
│       ├── spawner_tab.py            # Tab 2: Drone model spawner
│       ├── driver_tab.py             # Tab 3: SITL driver manager
│       ├── controller_tab.py         # Tab 4: MAVLink flight control
│       ├── simulation_tab.py         # Tab 5: End-to-end simulation
│       └── run_control_center.py     # Alternative launcher
└── Worlds/
    └── plains_env.sdf                # Grassland environment
```

---

## Component Status

### What Works (Tested & Verified)

| Component | Status | Notes |
|-----------|--------|-------|
| Gazebo server launch (headless) | ✅ Working | `gz sim -s -r` bypasses snap GUI crash |
| Gazebo GUI window | ✅ Working | Launched separately via `gz sim -g`, crash-tolerant |
| Drone spawning (iris_with_ardupilot) | ✅ Working | Via `gz service` EntityFactory |
| ArduPilot plugin loading | ✅ Working | LiftDrag, IMU, NavSat, JointStatePublisher all load |
| ArduCopter SITL (direct binary) | ✅ Working | Bypasses gnome-terminal snap crash |
| MAVProxy forwarding | ✅ Working | TCP 5760 → UDP 14550 bridge |
| MAVLink connect + GPS lock | ✅ Working | flight_controller.py heartbeat + GPS wait |
| Arming + takeoff | ✅ Working | GUIDED mode, MAV_CMD_NAV_TAKEOFF |
| Movement commands | ⚠️ Partial | Body-frame velocity works but heading drift causes path error |
| Landing + disarm | ✅ Working | LAND mode, detects disarm via heartbeat |
| .simulation file format | ✅ Working | JSON files scanned from ~/ROS2_Tools/Simulations/ |
| Dark theme GUI | ✅ Working | Consistent styling across all tabs |
| Process cleanup on exit | ✅ Working | SIGTERM to process groups + pkill fallback |
| SITL cleanup after mission | ✅ Working | ArduCopter/MAVProxy killed, Gazebo stays alive |

### Known Issues

| Issue | Severity | Root Cause | Workaround |
|-------|----------|------------|------------|
| Gazebo GUI crashes on VirtualBox | Low | snap's libpthread.so symbol conflict | GUI launched as separate process; crash doesn't affect server |
| gnome-terminal won't open | Low | Same snap libpthread conflict | All SITL launched as background processes, no terminal needed |
| Move commands have heading drift | Medium | `MAV_FRAME_BODY_OFFSET_NED` is relative to current heading; open-loop velocity control accumulates error | Use world-frame NED positioning instead |
| `sim_vehicle.py` unusable | Low | Depends on gnome-terminal which crashes | Direct `arducopter` + `mavproxy.py` launch |
| Driver tab uses `sim_vehicle.py` | ~~Medium~~ | ~~Built-in drivers still reference `sim_vehicle.py` which fails~~ | **Fixed** — driver works now |
| No multi-drone support | Low | Single MAVLink connection (UDP 14550), single SITL instance | Architecture supports it (GlobalState tracks multiple drones) but not yet wired |

---

## Architecture Assessment

### Strengths

**Separation of concerns** — Each tab is an independent module with its own file. `GlobalState` provides clean event-driven communication between tabs without tight coupling.

**Process resilience** — The headless server + optional GUI pattern is robust. Snap crashes, terminal failures, and GUI issues don't kill the simulation. Process groups with SIGTERM + pkill fallback ensures reliable cleanup.

**File-based configuration** — The `.simulation` format is clean, human-readable JSON. Users can create simulations via the GUI dialog or by hand-editing files. The directory scan pattern means no database or registry needed.

**Incremental complexity** — Individual tabs (Environment, Spawner, Driver, Controller) work independently for manual workflows. The Simulation tab orchestrates them together for automated runs. Users can mix and match.

### Weaknesses

**flight_controller.py movement model** — `move_relative` uses body-frame velocity commands with time-based distance estimation (`sleep(distance/speed)`). This is inherently imprecise because:
- Heading drift rotates the velocity vector
- Wind/physics perturbations aren't compensated
- No position feedback loop
- Stopping relies on zero-velocity command, not position hold

A better approach would be to compute target GPS/NED coordinates and use position-based commands with a feedback loop checking `GLOBAL_POSITION_INT`.

**Driver tab vs Simulation tab duplication** — The Driver tab still uses `sim_vehicle.py` wrappers, while the Simulation tab has its own direct-launch code. These should be unified so the Driver tab also works on VirtualBox.

**No telemetry visualization** — The Controller tab shows GPS coordinates but there's no map, altitude graph, or attitude display. The user is flying blind except for text coordinates.

**Error recovery is limited** — If a mid-flight step fails, the system does emergency land but doesn't offer retry, skip, or return-to-home options.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| OS | Ubuntu 24.04 LTS (VirtualBox guest) |
| Robot middleware | ROS2 Jazzy |
| Physics simulator | Gazebo Harmonic (gz-sim 8.9.0) |
| Flight controller | ArduPilot SITL (ArduCopter V4.7.0-dev) |
| MAVLink bridge | MAVProxy |
| MAVLink library | pymavlink |
| GUI framework | Python tkinter + ttk |
| Drone plugin | ardupilot_gazebo (ArduPilotPlugin) |
| Drone model | iris_with_ardupilot (quadcopter) |

---

## File Sizes

| File | Lines | Role |
|------|-------|------|
| simulation_tab.py | 1,348 | Largest — full orchestration + dialog |
| driver_tab.py | 537 | Driver management + custom driver dialog |
| controller_tab.py | 390 | MAVLink control + mission builder |
| spawner_tab.py | 290 | Model scanner + spawner |
| environment_tab.py | 270 | World launcher + preview |
| flight_controller.py | 230 | MAVLink drone abstraction |
| theme.py | 270 | Dark theme + terminal colors |
| global_state.py | 90 | Shared state singleton |
| main.py | 175 | Tab wiring + exit handling |

---

## Recommended Next Steps (Priority Order)

### 1. Fix movement precision (High)
Replace body-frame velocity commands with world-frame position targets. Compute target NED coordinates from current position + offset, then command `SET_POSITION_TARGET_LOCAL_NED` with position (not velocity) and poll `GLOBAL_POSITION_INT` until within tolerance.

### 2. Unify driver launch (Medium)
Port the direct `arducopter` + `mavproxy.py` launch pattern from `simulation_tab.py` into `driver_tab.py` so manual SITL launching also works on VirtualBox.

### 3. Add waypoint-based navigation (Medium)
Replace relative move commands with GPS waypoint missions using `MAV_CMD_NAV_WAYPOINT`. This gives ArduPilot's internal navigation controller (EKF + PID loops) full authority over path following, which is far more accurate than open-loop velocity.

### 4. Live telemetry display (Low)
Add a simple canvas or label panel showing altitude over time, heading, and battery. The data is already available via `GLOBAL_POSITION_INT` and `SYS_STATUS` messages.

### 5. More simulation files (Low)
Create additional `.simulation` files for different patterns: hover test, circle, figure-8, altitude hold test. These are just JSON files — no code changes needed.

### 6. Multi-drone support (Future)
The architecture already tracks multiple drones in `GlobalState.spawned_drones`. Extending to multiple SITL instances requires assigning different port numbers (`-I0`, `-I1`) and connecting multiple `DroneController` instances.

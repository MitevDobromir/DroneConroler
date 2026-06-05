#!/bin/bash
# launch_sitl.sh - Launch ArduPilot SITL (arducopter/arduplane/ardurover)
#                  plus MAVProxy. Replaces sim_vehicle.py for the Driver tab.
#
# Why a helper script?
#   sim_vehicle.py is the upstream ArduPilot SITL launcher. On Ubuntu 24.04
#   inside VirtualBox its child processes pick up snap libraries and
#   crash with libpthread symbol-lookup errors. The Simulation tab fixes
#   this by launching the underlying binaries directly with a cleaned
#   LD_LIBRARY_PATH. This script does the same for the Driver tab.
#
# Usage:
#   launch_sitl.sh <vehicle> [instance]
#       vehicle  = copter | plane | rover
#       instance = 0,1,2... (default 0)
#
# This script expects setup_ardupilot_env.sh to have been sourced
# already. The Driver tab does that wrapping before invoking the
# helper. To run from a plain terminal:
#
#   source ~/ROS2_Tools/ArduPilot/setup_ardupilot_env.sh
#   ~/ROS2_Tools/Scripts/launch_sitl.sh copter 0
#
# MAVLink endpoints (instance N shifts each by 2*N):
#   udp:127.0.0.1:14550  - primary
#   udp:127.0.0.1:14551  - secondary
#
# SITL TCP master port:
#   tcp:127.0.0.1:5760  + (instance * 10)

set -u

VEHICLE="${1:-}"
INSTANCE="${2:-0}"

if [ -z "$VEHICLE" ]; then
    echo "usage: $(basename "$0") <copter|plane|rover> [instance]" >&2
    exit 2
fi

case "$VEHICLE" in
    copter) BINARY=arducopter; DEFAULTS_NAME=copter.parm ;;
    plane)  BINARY=arduplane;  DEFAULTS_NAME=plane.parm  ;;
    rover)  BINARY=ardurover;  DEFAULTS_NAME=rover.parm  ;;
    *)
        echo "ERROR: vehicle must be copter, plane, or rover (got: '$VEHICLE')" >&2
        exit 2
        ;;
esac

# Resolve ArduPilot base (set by setup_ardupilot_env.sh) with a fallback.
ARDUPILOT_BASE="${ARDUPILOT_BASE:-$HOME/ROS2_Tools/ArduPilot}"

# The compiled SITL binary lives in the build tree, NOT on PATH.
# (setup_ardupilot_env.sh only adds Tools/autotest, which contains
# sim_vehicle.py, not the actual SITL executable.) Match the path
# simulation_tab.py uses: $ARDUPILOT_HOME/build/sitl/bin/<binary>
BINARY_PATH="$ARDUPILOT_BASE/ardupilot/build/sitl/bin/$BINARY"
DEFAULTS_FILE="$ARDUPILOT_BASE/ardupilot/Tools/autotest/default_params/$DEFAULTS_NAME"

if [ ! -x "$BINARY_PATH" ]; then
    echo "ERROR: SITL binary not found or not executable:" >&2
    echo "       $BINARY_PATH" >&2
    echo "       Build it with: cd $ARDUPILOT_BASE/ardupilot && ./waf $VEHICLE" >&2
    exit 1
fi

if [ ! -f "$DEFAULTS_FILE" ]; then
    echo "ERROR: defaults file not found: $DEFAULTS_FILE" >&2
    exit 1
fi

# Compute port offsets
TCP_PORT=$(( 5760 + INSTANCE * 10 ))
UDP_OUT_A=$(( 14550 + INSTANCE * 10 ))
UDP_OUT_B=$(( 14551 + INSTANCE * 10 ))

SITL_PID=""

cleanup() {
    echo ""
    echo "[launch_sitl] Shutting down..."
    if [ -n "$SITL_PID" ] && kill -0 "$SITL_PID" 2>/dev/null; then
        kill -TERM "$SITL_PID" 2>/dev/null || true
        for _ in 1 2 3 4 5; do
            kill -0 "$SITL_PID" 2>/dev/null || break
            sleep 0.5
        done
        kill -KILL "$SITL_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "[launch_sitl] $BINARY -I$INSTANCE"
echo "[launch_sitl]   binary   : $BINARY_PATH"
echo "[launch_sitl]   defaults : $DEFAULTS_FILE"
echo "[launch_sitl]   TCP      : 127.0.0.1:$TCP_PORT"
echo "[launch_sitl]   UDP out  : 127.0.0.1:$UDP_OUT_A , 127.0.0.1:$UDP_OUT_B"
echo ""

# Launch SITL binary in background using the absolute build path.
# Note: -S (synthetic-clock) is deprecated and ignored by modern arducopter,
# and --slowdown is not a valid flag (it caused arducopter to dump help and
# exit). We use only the flags that current arducopter actually accepts.
"$BINARY_PATH" --model JSON --speedup 1 \
    --defaults "$DEFAULTS_FILE" -I"$INSTANCE" &
SITL_PID=$!

# Give SITL time to bind its TCP port before MAVProxy tries to connect.
sleep 4

if ! kill -0 "$SITL_PID" 2>/dev/null; then
    echo "[launch_sitl] ERROR: $BINARY exited before MAVProxy startup" >&2
    exit 1
fi

# MAVProxy in foreground so its output streams to the Driver tab terminal.
exec mavproxy.py \
    --master "tcp:127.0.0.1:$TCP_PORT" \
    --out "udp:127.0.0.1:$UDP_OUT_A" \
    --out "udp:127.0.0.1:$UDP_OUT_B" \
    --non-interactive
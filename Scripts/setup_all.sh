#!/bin/bash
# =============================================================================
# setup_drone_control_center.sh
# -----------------------------------------------------------------------------
# One-shot, from-scratch setup for the Drone Control Center on a fresh
# Ubuntu 24.04 LTS machine (physical or VirtualBox).
#
# It downloads and installs EVERYTHING the project needs:
#   1.  UTF-8 locale            (required by ROS 2)
#   2.  ROS 2 Jazzy + dev tools (apt repo via ros2-apt-source)
#   3.  Gazebo Harmonic + ros_gz integration
#   4.  All system / Python / GStreamer / Mesa dependencies
#   5.  pymavlink + MAVProxy
#   6.  GeographicLib datasets  (for MAVROS)
#   7.  ArduPilot (ArduCopter 4.5) + SITL build
#   8.  ardupilot_gazebo plugin (built for Harmonic)
#   9.  ~/ROS2_Tools workspace layout + environment script + ~/.bashrc hook
#
# This script SUPERSEDES the old install_dependencies.sh + setup_ardupilot.sh.
# It is idempotent: re-running skips anything already present.
#
# Usage:   chmod +x setup_drone_control_center.sh
#          ./setup_drone_control_center.sh
# (Do NOT run as root; it calls sudo only where needed.)
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
print_status()  { echo -e "${GREEN}[INFO]${NC} $1"; }
print_step()    { echo -e "\n${BLUE}==== $1 ====${NC}"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

if [ "$(id -u)" -eq 0 ]; then
    print_error "Do not run this script as root. Run it as your normal user; it uses sudo when required."
    exit 1
fi

# Keep sudo alive for the whole run
sudo -v
( while true; do sudo -n true; sleep 50; kill -0 "$$" 2>/dev/null || exit; done ) &
SUDO_KEEPALIVE_PID=$!
trap 'kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true' EXIT

ROS_DISTRO=jazzy
WORKSPACE_DIR="$HOME/ROS2_Tools"
ARDUPILOT_DIR="$WORKSPACE_DIR/ArduPilot"
NPROC="$(nproc)"

# -----------------------------------------------------------------------------
print_step "STEP 1 / 9 : UTF-8 locale"
# -----------------------------------------------------------------------------
if ! locale | grep -q "UTF-8"; then
    sudo apt update
    sudo apt install -y locales
    sudo locale-gen en_US en_US.UTF-8
    sudo update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
    export LANG=en_US.UTF-8
    print_status "Locale set to en_US.UTF-8"
else
    print_status "UTF-8 locale already configured"
fi

# -----------------------------------------------------------------------------
print_step "STEP 2 / 9 : APT repositories (Universe, ROS 2, Gazebo)"
# -----------------------------------------------------------------------------
sudo apt install -y software-properties-common curl wget gnupg lsb-release
sudo add-apt-repository -y universe

# --- ROS 2 apt source (official ros2-apt-source package) ---
if [ ! -f /etc/apt/sources.list.d/ros2.sources ] && [ ! -f /etc/apt/sources.list.d/ros2.list ]; then
    print_status "Adding ROS 2 apt repository..."
    ROS_APT_SOURCE_VERSION="$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
        | grep -F "tag_name" | awk -F\" '{print $4}')"
    CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
    curl -L -o /tmp/ros2-apt-source.deb \
        "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.${CODENAME}_all.deb"
    sudo dpkg -i /tmp/ros2-apt-source.deb
    rm -f /tmp/ros2-apt-source.deb
else
    print_status "ROS 2 apt repository already present"
fi

# --- Gazebo (OSRF) apt source ---
if ! grep -rq "packages.osrfoundation.org" /etc/apt/sources.list.d/ 2>/dev/null; then
    print_status "Adding Gazebo apt repository..."
    sudo wget -q https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
        | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
else
    print_status "Gazebo apt repository already present"
fi

sudo apt update

# -----------------------------------------------------------------------------
print_step "STEP 3 / 9 : ROS 2 Jazzy + Gazebo Harmonic"
# -----------------------------------------------------------------------------
if [ ! -d "/opt/ros/${ROS_DISTRO}" ]; then
    print_status "Installing ros-${ROS_DISTRO}-desktop (this downloads several GB)..."
    sudo apt install -y "ros-${ROS_DISTRO}-desktop" ros-dev-tools
else
    print_status "ROS 2 ${ROS_DISTRO} already installed"
fi

if ! command -v gz &>/dev/null; then
    print_status "Installing Gazebo Harmonic..."
    sudo apt install -y gz-harmonic
else
    print_status "Gazebo already installed ($(gz sim --version 2>/dev/null | head -1))"
fi

# -----------------------------------------------------------------------------
print_step "STEP 4 / 9 : System, Python, GStreamer, Mesa & ROS dependencies"
# -----------------------------------------------------------------------------
print_status "Build tools..."
sudo apt install -y \
    build-essential cmake pkg-config git wget curl \
    python3-pip python3-dev python3-venv

print_status "ArduPilot / plugin build libraries..."
sudo apt install -y \
    libeigen3-dev libxml2-dev libxml2-utils \
    protobuf-compiler libprotobuf-dev libprotoc-dev \
    geographiclib-tools \
    libopencv-dev rapidjson-dev

print_status "Gazebo Harmonic development libraries (for the ardupilot_gazebo plugin)..."
sudo apt install -y \
    libgz-sim8-dev libgz-common5-dev libgz-msgs10-dev \
    libgz-transport13-dev libgz-sensors8-dev libgz-rendering8-dev \
    libgz-math7-dev libgz-utils2-dev libgz-plugin2-dev

print_status "Python libraries used by the GUI (tkinter + Pillow + helpers)..."
sudo apt install -y \
    python3-setuptools python3-numpy python3-yaml python3-matplotlib \
    python3-serial python3-lxml python3-future python3-empy \
    python3-tk python3-pil python3-pil.imagetk

print_status "GStreamer (camera streaming; 'ugly' set is required for H.264 decode)..."
sudo apt install -y \
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-gl

print_status "Mesa software-rendering drivers (llvmpipe fallback for VirtualBox)..."
sudo apt install -y libgl1-mesa-dri mesa-utils
sudo apt install -y mesa-vulkan-drivers || print_warning "mesa-vulkan-drivers unavailable; llvmpipe will still work"

print_status "ROS 2 packages (MAVROS + ros_gz bridge)..."
sudo apt install -y \
    "ros-${ROS_DISTRO}-mavros" "ros-${ROS_DISTRO}-mavros-extras" \
    "ros-${ROS_DISTRO}-geographic-msgs" "ros-${ROS_DISTRO}-sensor-msgs" \
    "ros-${ROS_DISTRO}-geometry-msgs" \
    "ros-${ROS_DISTRO}-ros-gz" "ros-${ROS_DISTRO}-ros-gz-sim" \
    "ros-${ROS_DISTRO}-ros-gz-bridge" "ros-${ROS_DISTRO}-ros-gz-interfaces"

# -----------------------------------------------------------------------------
print_step "STEP 5 / 9 : Python pip packages (pymavlink, MAVProxy)"
# -----------------------------------------------------------------------------
pip3 install --user --break-system-packages pymavlink MAVProxy pillow
print_status "pymavlink + MAVProxy installed"

# -----------------------------------------------------------------------------
print_step "STEP 6 / 9 : GeographicLib datasets (MAVROS geoid model)"
# -----------------------------------------------------------------------------
if wget -q -O /tmp/install_geographiclib_datasets.sh \
    https://raw.githubusercontent.com/mavlink/mavros/master/mavros/scripts/install_geographiclib_datasets.sh; then
    sudo bash /tmp/install_geographiclib_datasets.sh && print_status "GeographicLib datasets installed"
    rm -f /tmp/install_geographiclib_datasets.sh
else
    print_warning "Could not download GeographicLib datasets script; continuing"
fi

# -----------------------------------------------------------------------------
print_step "STEP 7 / 9 : ArduPilot (ArduCopter 4.5) + SITL"
# -----------------------------------------------------------------------------
mkdir -p "$ARDUPILOT_DIR"
cd "$ARDUPILOT_DIR"

if [ ! -d "ardupilot" ]; then
    print_status "Cloning ArduPilot (branch Copter-4.5)..."
    git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git
    cd ardupilot
    git checkout Copter-4.5
    git submodule update --init --recursive
    print_status "Installing ArduPilot prerequisites (official installer)..."
    Tools/environment_install/install-prereqs-ubuntu.sh -y || print_warning "Some ArduPilot prereqs reported issues; continuing"
    cd "$ARDUPILOT_DIR"
else
    print_status "ArduPilot already cloned; updating submodules..."
    cd ardupilot && git submodule update --init --recursive && cd "$ARDUPILOT_DIR"
fi

print_status "Building ArduCopter SITL (this may take several minutes)..."
cd "$ARDUPILOT_DIR/ardupilot"
# shellcheck disable=SC1090
[ -f "$HOME/.profile" ] && source "$HOME/.profile" || true
export PATH="$PATH:$HOME/.local/bin"
./waf configure --board sitl
./waf copter
print_status "ArduCopter SITL built"

# -----------------------------------------------------------------------------
print_step "STEP 8 / 9 : ardupilot_gazebo plugin (built for Harmonic)"
# -----------------------------------------------------------------------------
cd "$ARDUPILOT_DIR"
if [ ! -d "ardupilot_gazebo" ]; then
    print_status "Cloning ardupilot_gazebo..."
    git clone https://github.com/ArduPilot/ardupilot_gazebo.git
else
    print_status "ardupilot_gazebo already cloned; pulling latest..."
    cd ardupilot_gazebo && git pull --ff-only || true; cd "$ARDUPILOT_DIR"
fi

cd "$ARDUPILOT_DIR/ardupilot_gazebo"
export GZ_VERSION=harmonic
# Force Harmonic (gz-sim8) library versions if the CMakeLists still targets gz-sim7 (Garden)
if grep -q "gz-sim7" CMakeLists.txt 2>/dev/null; then
    print_status "Patching CMakeLists.txt: gz-sim7 -> gz-sim8 (Garden -> Harmonic)"
    sed -i 's/gz-rendering7/gz-rendering8/g; s/gz-sim7/gz-sim8/g' CMakeLists.txt
fi
rm -rf build && mkdir build && cd build
# shellcheck disable=SC1091
source "/opt/ros/${ROS_DISTRO}/setup.bash"
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j"$NPROC"
if [ ! -f "libArduPilotPlugin.so" ]; then
    print_error "ardupilot_gazebo plugin build failed (libArduPilotPlugin.so not produced)"
    exit 1
fi
print_status "ardupilot_gazebo plugin built"

# -----------------------------------------------------------------------------
print_step "STEP 9 / 9 : Workspace layout + environment script"
# -----------------------------------------------------------------------------
# Project content (Software, Worlds, Models, Scripts, Simulations, Drivers) is
# expected to live under ~/ROS2_Tools. Ensure the runtime directories exist.
mkdir -p "$WORKSPACE_DIR"/{Models,Models/previews,Worlds,Simulations,Drivers}
print_status "Ensured workspace directories under $WORKSPACE_DIR"

ENV_SCRIPT="$ARDUPILOT_DIR/setup_ardupilot_env.sh"
cat > "$ENV_SCRIPT" << 'ENVEOF'
#!/bin/bash
# ArduPilot + Gazebo + Drone Control Center environment

# ROS 2
source /opt/ros/jazzy/setup.bash

# Gazebo Harmonic
export GZ_VERSION=harmonic

# Software rendering (required inside VirtualBox: no Vulkan/GPU passthrough)
export LIBGL_ALWAYS_SOFTWARE=1

# Paths
ROS2_TOOLS="$HOME/ROS2_Tools"
ARDUPILOT_BASE="$ROS2_TOOLS/ArduPilot"
ARDUPILOT_PLUGIN_PATH="$ARDUPILOT_BASE/ardupilot_gazebo/build"
ROS_PLUGIN_PATHS="$(find /opt/ros/jazzy -name lib -type d 2>/dev/null | tr '\n' ':' | sed 's/:$//')"

# Gazebo plugin path (dedup colons)
export GZ_SIM_SYSTEM_PLUGIN_PATH="$ARDUPILOT_PLUGIN_PATH:$ROS_PLUGIN_PATHS:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$(echo "$GZ_SIM_SYSTEM_PLUGIN_PATH" | sed 's/::/:/g; s/^://; s/:$//')"

# Gazebo resource path: plugin assets + project models & worlds
export GZ_SIM_RESOURCE_PATH="$ARDUPILOT_BASE/ardupilot_gazebo/models:$ARDUPILOT_BASE/ardupilot_gazebo/worlds:$ROS2_TOOLS/Models:$ROS2_TOOLS/Worlds:${GZ_SIM_RESOURCE_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$(echo "$GZ_SIM_RESOURCE_PATH" | sed 's/::/:/g; s/^://; s/:$//')"

# ArduPilot autotest tools + user pip bin
export PATH="$ARDUPILOT_BASE/ardupilot/Tools/autotest:$HOME/.local/bin:$PATH"

if [ -f "$ARDUPILOT_PLUGIN_PATH/libArduPilotPlugin.so" ]; then
    echo "ArduPilot + Gazebo environment loaded (plugin OK)."
else
    echo "WARNING: ArduPilot plugin not found at $ARDUPILOT_PLUGIN_PATH"
fi
ENVEOF
chmod +x "$ENV_SCRIPT"
print_status "Environment script written: $ENV_SCRIPT"

# Hook into ~/.bashrc once
if ! grep -qF "source $ENV_SCRIPT" "$HOME/.bashrc"; then
    {
        echo ""
        echo "# Drone Control Center environment"
        echo "source $ENV_SCRIPT"
    } >> "$HOME/.bashrc"
    print_status "Added environment hook to ~/.bashrc"
else
    print_status "~/.bashrc already sources the environment script"
fi

# -----------------------------------------------------------------------------
echo ""
print_status "============================================================"
print_status " SETUP COMPLETE"
print_status "============================================================"
echo ""
print_status "Next steps:"
print_status "  1. Open a NEW terminal (so the environment loads)."
print_status "  2. Launch the Drone Control Center:"
print_status "        cd ~/ROS2_Tools/Software && python3 -m GUI"
echo ""
print_status "Installed: ROS 2 ${ROS_DISTRO}, Gazebo Harmonic, ArduCopter 4.5 SITL,"
print_status "ardupilot_gazebo plugin, MAVROS, MAVProxy, GStreamer (incl. ugly/H.264),"
print_status "tkinter + Pillow, and Mesa software-rendering drivers."

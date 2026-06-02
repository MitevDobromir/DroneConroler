#!/bin/bash
# Complete ArduPilot + Gazebo Setup for Ubuntu 24.04 + ROS2 Jazzy

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

WORKSPACE_DIR="$HOME/ROS2_Tools/ArduPilot"
mkdir -p $WORKSPACE_DIR
cd $WORKSPACE_DIR

print_status "=== Step 1: Installing Gazebo Harmonic ==="
if ! command -v gz &> /dev/null; then
    print_status "Adding Gazebo repository..."
    sudo wget https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
    
    sudo apt update
    sudo apt install -y gz-harmonic
    print_status "✅ Gazebo Harmonic installed"
else
    print_status "✅ Gazebo already installed"
fi

print_status "=== Step 2: Installing Dependencies ==="
sudo apt update
sudo apt install -y \
    libgz-sim8-dev \
    rapidjson-dev \
    libopencv-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-gl \
    python3-pip \
    python3-lxml

print_status "=== Step 3: Cloning ArduPilot ==="
if [ ! -d "ardupilot" ]; then
    git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git
    cd ardupilot
    git checkout Copter-4.5
    git submodule update --init --recursive
    
    # Install ArduPilot prerequisites
    print_status "Installing ArduPilot prerequisites..."
    Tools/environment_install/install-prereqs-ubuntu.sh -y
    cd ..
else
    print_status "ArduPilot already exists"
fi

print_status "=== Step 4: Cloning ArduPilot Gazebo Plugin ==="
if [ ! -d "ardupilot_gazebo" ]; then
    git clone https://github.com/ArduPilot/ardupilot_gazebo.git
else
    print_status "ArduPilot Gazebo plugin already exists"
    cd ardupilot_gazebo
    git pull
    cd ..
fi

print_status "=== Step 5: Building ArduPilot Gazebo Plugin ==="
cd ardupilot_gazebo

# Set GZ_VERSION before building
export GZ_VERSION=harmonic

# Update CMakeLists.txt to use version 8 if needed
if grep -q "gz-sim7" CMakeLists.txt; then
    print_status "Updating CMakeLists.txt for Gazebo Harmonic..."
    sed -i 's/gz-rendering7/gz-rendering8/g' CMakeLists.txt
    sed -i 's/gz-sim7/gz-sim8/g' CMakeLists.txt
fi

rm -rf build
mkdir build
cd build

cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j$(nproc)

if [ ! -f "libArduPilotPlugin.so" ]; then
    print_error "Plugin build failed!"
    exit 1
fi

print_status "✅ ArduPilot plugin built successfully"

print_status "=== Step 6: Setting up Environment ==="
ENV_SCRIPT="$WORKSPACE_DIR/setup_ardupilot_env.sh"
cat > $ENV_SCRIPT << 'ENVEOF'
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
ENVEOF

chmod +x $ENV_SCRIPT

# Add to bashrc if not already there
if ! grep -qF "source $ENV_SCRIPT" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# ArduPilot + Gazebo Environment" >> ~/.bashrc
    echo "source $ENV_SCRIPT" >> ~/.bashrc
    print_status "✅ Environment setup added to ~/.bashrc"
fi

source "$ENV_SCRIPT"

print_status "=== Step 7: Building ArduPilot SITL ==="
cd $WORKSPACE_DIR/ardupilot

# Configure for SITL
print_status "Configuring ArduPilot for SITL..."
./waf configure --board sitl

# Build ArduCopter
print_status "Building ArduCopter (this may take several minutes)..."
./waf copter

if [ $? -eq 0 ]; then
    print_status "✅ ArduCopter built successfully"
else
    print_error "ArduCopter build failed!"
    exit 1
fi

print_status ""
print_status "🎉 SETUP COMPLETE!"
print_status ""
print_status "📋 Next Steps:"
print_status "1. Open a NEW terminal (to load environment)"
print_status "2. Test with your cube drone:"
print_status "   Terminal 1: cd ~/ROS2_Tools/Scripts && ./launch_env.sh plains_env.sdf"
print_status "              ./spawn_drone.sh drone1 Cube 0 0 0.2"
print_status "   Terminal 2: cd ~/ROS2_Tools/ArduPilot/ardupilot"
print_status "              sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --console --map"
print_status ""
print_status "3. In MAVProxy console:"
print_status "   mode guided"
print_status "   arm throttle"
print_status "   takeoff 5"
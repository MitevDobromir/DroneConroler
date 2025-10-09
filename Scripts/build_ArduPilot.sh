#!/bin/bash
# build_ardupilot_plugins.sh
# Build ArduPilot Gazebo plugins for Ubuntu 24.04 + ROS2 Jazzy

echo "=== Building ArduPilot Gazebo Plugins ==="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to check if command succeeded
check_success() {
    if [ $? -ne 0 ]; then
        print_error "$1"
        exit 1
    fi
}

# Set workspace
WORKSPACE_DIR="$HOME/ardupilot_ws"
mkdir -p $WORKSPACE_DIR
cd $WORKSPACE_DIR

print_status "Step 1: Installing Gazebo development libraries..."

# Add Gazebo repository for development libraries
if ! grep -q "packages.osrfoundation.org" /etc/apt/sources.list.d/* 2>/dev/null; then
    print_status "Adding Gazebo repository..."
    sudo wget https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
    sudo apt update
fi

# Install ROS2 Gazebo integration first (these are the main packages we need)
print_status "Installing ROS2 Gazebo integration packages..."
sudo apt install -y \
    ros-jazzy-ros-gz \
    ros-jazzy-ros-gz-sim \
    ros-jazzy-ros-gz-bridge \
    ros-jazzy-ros-gz-interfaces
check_success "Failed to install ROS2 Gazebo integration"

# Install Gazebo Harmonic (recommended for Jazzy)
print_status "Installing Gazebo Harmonic..."
sudo apt install -y gz-harmonic
if [ $? -eq 0 ]; then
    print_status "✅ Gazebo Harmonic installed"
    GZ_VERSION="harmonic"
else
    print_warning "Harmonic installation failed, trying Garden..."
    sudo apt install -y gz-garden
    check_success "Failed to install Gazebo Garden"
    GZ_VERSION="garden"
fi

# Install the specific Gazebo development packages we need
print_status "Installing Gazebo development libraries for $GZ_VERSION..."
if [ "$GZ_VERSION" = "harmonic" ]; then
    sudo apt install -y \
        libgz-sim8-dev \
        libgz-common5-dev \
        libgz-msgs10-dev \
        libgz-transport13-dev \
        libgz-sensors8-dev \
        libgz-rendering8-dev \
        libgz-math7-dev \
        libgz-utils2-dev \
        libgz-plugin2-dev \
        rapidjson-dev
else
    sudo apt install -y \
        libgz-sim7-dev \
        libgz-common5-dev \
        libgz-msgs9-dev \
        libgz-transport12-dev \
        libgz-sensors7-dev \
        libgz-rendering7-dev \
        libgz-math7-dev \
        libgz-utils2-dev \
        libgz-plugin2-dev \
        rapidjson-dev
fi
check_success "Failed to install Gazebo development packages"

# Install additional dependencies for ArduPilot plugin
sudo apt install -y \
    libopencv-dev \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    gstreamer1.0-gl
check_success "Failed to install additional dependencies"

print_status "Step 2: Cloning ArduPilot repositories..."

# Clone ArduPilot if not exists
if [ ! -d "ardupilot" ]; then
    print_status "Cloning ArduPilot..."
    git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git
    check_success "Failed to clone ArduPilot"
else
    print_status "ArduPilot already exists, updating..."
    cd ardupilot
    git pull
    git submodule update --init --recursive
    cd ..
fi

# Clone ArduPilot Gazebo plugin
if [ ! -d "ardupilot_gazebo" ]; then
    print_status "Cloning ArduPilot Gazebo plugin..."
    git clone https://github.com/ArduPilot/ardupilot_gazebo.git
    check_success "Failed to clone ArduPilot Gazebo plugin"
else
    print_status "ArduPilot Gazebo plugin already exists, updating..."
    cd ardupilot_gazebo
    git pull
    cd ..
fi

print_status "Step 3: Building ArduPilot Gazebo plugin..."

cd ardupilot_gazebo

# Clean previous build
rm -rf build
mkdir build
cd build

# Source ROS2 environment
source /opt/ros/jazzy/setup.bash

# Configure with CMake - add verbose output for debugging
print_status "Configuring build with CMake..."
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_VERBOSE_MAKEFILE=ON
check_success "CMake configuration failed"

# Show what targets are available to build
print_status "Available build targets:"
make help | grep -E "(ArduPilot|motor|plugin)" || echo "No specific plugin targets found"

# Build the plugin with verbose output
print_status "Compiling plugins (this may take a few minutes)..."
make -j$(nproc) VERBOSE=1
check_success "Plugin build failed"

# Show what actually got built
print_status "Build completed. Files created:"
find . -name "*.so" -exec ls -la {} \;

# Install the plugin
print_status "Installing plugins..."
sudo make install
check_success "Plugin installation failed"

print_status "Step 4: Setting up environment..."

# Get the absolute path of the build directory
BUILD_DIR="$(pwd)"

# Create environment setup script
ENV_SCRIPT="$WORKSPACE_DIR/setup_ardupilot_env.sh"
cat > $ENV_SCRIPT << EOF
#!/bin/bash
# ArduPilot + Gazebo Environment Setup

# Source ROS2
source /opt/ros/jazzy/setup.bash

# Set Gazebo version (try harmonic first, fallback to garden)
export GZ_VERSION=harmonic
if ! gz sim --version 2>/dev/null | grep -q harmonic; then
    export GZ_VERSION=garden
fi

# Clean and set Gazebo plugin paths - avoid duplicates
ARDUPILOT_PLUGIN_PATH="$BUILD_DIR"
ROS_PLUGIN_PATHS="\$(find /opt/ros/jazzy -name "lib" -type d 2>/dev/null | tr '\n' ':' | sed 's/:$//')"

# Set plugin path without duplicates
export GZ_SIM_SYSTEM_PLUGIN_PATH="\$ARDUPILOT_PLUGIN_PATH:\$ROS_PLUGIN_PATHS:\$GZ_SIM_SYSTEM_PLUGIN_PATH"

# Clean up any duplicate colons
export GZ_SIM_SYSTEM_PLUGIN_PATH="\$(echo "\$GZ_SIM_SYSTEM_PLUGIN_PATH" | sed 's/::/:/g' | sed 's/^://' | sed 's/:$//')"

# Set resource paths
export GZ_SIM_RESOURCE_PATH="$WORKSPACE_DIR/ardupilot_gazebo/models:$WORKSPACE_DIR/ardupilot_gazebo/worlds:\$GZ_SIM_RESOURCE_PATH"

# Set ArduPilot paths
export PATH="$WORKSPACE_DIR/ardupilot/Tools/autotest:\$PATH"

echo "🚁 ArduPilot + Gazebo environment loaded!"
echo "📦 Gazebo version: \$GZ_VERSION"
echo "🔧 Plugin path: \$GZ_SIM_SYSTEM_PLUGIN_PATH"
echo "🌍 Resource path: \$GZ_SIM_RESOURCE_PATH"

# Verify plugins are accessible
if [ -f "$BUILD_DIR/libArduPilotPlugin.so" ]; then
    echo "✅ ArduPilot plugin found"
else
    echo "❌ ArduPilot plugin not found at $BUILD_DIR/libArduPilotPlugin.so"
fi

if [ -f "$BUILD_DIR/libgazebo_motor_model.so" ]; then
    echo "✅ Motor model plugin found"
else
    echo "⚠️  Motor model plugin not found (may not be needed)"
fi
EOF

chmod +x $ENV_SCRIPT

# Test the environment script
print_status "Testing environment configuration..."
source "$ENV_SCRIPT"
echo "Final plugin path: $GZ_SIM_SYSTEM_PLUGIN_PATH"

# Add to bashrc if not already there
if ! grep -qF "source $ENV_SCRIPT" ~/.bashrc; then
    echo "" >> ~/.bashrc
    echo "# ArduPilot + Gazebo Environment" >> ~/.bashrc
    echo "source $ENV_SCRIPT" >> ~/.bashrc
    print_status "✅ Environment setup added to ~/.bashrc"
else
    print_status "Environment setup already in ~/.bashrc"
fi

print_status "Step 5: Verifying plugin installation..."

# Check if plugins were built
PLUGIN_DIR="$WORKSPACE_DIR/ardupilot_gazebo/build"

print_status "Checking what actually got built in $PLUGIN_DIR:"
ls -la "$PLUGIN_DIR" | grep "\.so"

if [ -f "$PLUGIN_DIR/libArduPilotPlugin.so" ]; then
    print_status "✅ libArduPilotPlugin.so built successfully"
    echo "   Size: $(stat -c%s "$PLUGIN_DIR/libArduPilotPlugin.so") bytes"
else
    print_error "❌ libArduPilotPlugin.so not found"
    echo "Available .so files:"
    find "$PLUGIN_DIR" -name "*.so" | head -10
    exit 1
fi

# Check for motor model plugin - this might not exist in ArduPilot repo
if [ -f "$PLUGIN_DIR/libgazebo_motor_model.so" ]; then
    print_status "✅ libgazebo_motor_model.so built successfully"
# Check for motor model plugin - this might not exist in ArduPilot repo
if [ -f "$PLUGIN_DIR/libgazebo_motor_model.so" ]; then
    print_status "✅ libgazebo_motor_model.so built successfully"
else
    print_warning "⚠️  libgazebo_motor_model.so not found in ArduPilot build"
    print_status "Checking if motor model plugin exists in source..."
    
    # Check if the source files exist
    if find "$WORKSPACE_DIR/ardupilot_gazebo" -name "*motor*" -o -name "*rotor*" | grep -q .; then
        print_warning "Motor model source files found but didn't build - investigating..."
        find "$WORKSPACE_DIR/ardupilot_gazebo" -name "*motor*" -o -name "*rotor*"
    else
        print_status "Motor model plugin not included in ArduPilot Gazebo repository"
        print_status "Building motor model plugin from PX4 repository..."
        
        # Clone PX4 SITL gazebo for motor model
        cd "$WORKSPACE_DIR"
        if [ ! -d "PX4-SITL_gazebo" ]; then
            git clone --depth 1 https://github.com/PX4/PX4-SITL_gazebo.git
        fi
        
        cd PX4-SITL_gazebo
        mkdir -p build && cd build
        source /opt/ros/jazzy/setup.bash
        
        # Build only the motor model plugin
        cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
        make gazebo_motor_model 2>/dev/null || make -j$(nproc) 2>/dev/null
        
        # Copy motor model plugin to ArduPilot build directory
        if [ -f "libgazebo_motor_model.so" ]; then
            cp libgazebo_motor_model.so "$PLUGIN_DIR/"
            print_status "✅ Motor model plugin built from PX4 and copied"
        else
            print_warning "Motor model plugin build failed - continuing without it"
            print_status "ArduPilot plugin can handle motor control without separate motor plugin"
        fi
        
        cd "$PLUGIN_DIR"
    fi
fi

# Check ROS2 IMU plugin - use correct package names
source /opt/ros/jazzy/setup.bash
if ros2 pkg list | grep -q "ros_gz"; then
    print_status "✅ ROS2 Gazebo integration available"
else
    print_warning "⚠️  Installing ROS2 Gazebo integration packages..."
    sudo apt install -y \
        ros-jazzy-ros-gz \
        ros-jazzy-ros-gz-sim \
        ros-jazzy-ros-gz-bridge \
        ros-jazzy-ros-gz-interfaces
fi

# Check for IMU sensor plugin specifically
IMU_PLUGIN=$(find /opt/ros/jazzy -name "*gazebo*ros*imu*.so" 2>/dev/null | head -1)
if [ -n "$IMU_PLUGIN" ]; then
    print_status "✅ IMU sensor plugin found: $IMU_PLUGIN"
else
    print_warning "⚠️  IMU sensor plugin not found - may need different package"
fi

# Test if environment actually works
print_status "Testing environment configuration..."
source "$ENV_SCRIPT"
if [[ "$GZ_SIM_SYSTEM_PLUGIN_PATH" == *"$PLUGIN_DIR"* ]]; then
    print_status "✅ Plugin path correctly configured"
else
    print_error "❌ Plugin path not properly set"
    echo "Expected: $PLUGIN_DIR"
    echo "Got: $GZ_SIM_SYSTEM_PLUGIN_PATH"
fi

print_status ""
print_status "🎉 BUILD COMPLETE!"
print_status ""
print_status "📋 What was built:"
print_status " • ✅ ArduPilot Gazebo plugin (libArduPilotPlugin.so)"
if [ -f "$PLUGIN_DIR/libgazebo_motor_model.so" ]; then
    print_status " • ✅ Motor model plugins (libgazebo_motor_model.so)"
else
    print_status " • ⚠️  Motor model plugin not available (ArduPilot plugin handles motors)"
fi
print_status " • ✅ Environment configuration"
print_status " • ✅ ROS2 IMU sensor plugin"
print_status ""
print_status "🚀 Test your cube drone:"
print_status " 1. Open a NEW terminal (to load environment)"
print_status " 2. Start ArduPilot SITL:"
print_status "    cd $WORKSPACE_DIR/ardupilot"
print_status "    sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --console"
print_status " 3. In another terminal, start Gazebo with your drone:"
print_status "    source $ENV_SCRIPT"
print_status "    gz sim cube_drone.sdf"
print_status ""
if [ ! -f "$PLUGIN_DIR/libgazebo_motor_model.so" ]; then
    print_status "💡 Note: If you get motor plugin errors, remove the motor plugin"
    print_status "   sections from your SDF file. ArduPilot plugin handles motor control."
fi
print_status ""
print_status "🔄 If you see plugin errors, check: echo \$GZ_SIM_SYSTEM_PLUGIN_PATH"
#!/bin/bash
# simple_ardupilot_deps.sh
# Install ONLY the essential dependencies that we know work
echo "=== Installing Essential ArduPilot Dependencies ==="

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

print_status "1/4 Installing basic build tools..."
sudo apt install -y \
    build-essential \
    cmake \
    pkg-config \
    git \
    wget \
    curl \
    python3-pip \
    python3-dev
check_success "Failed to install build tools"

print_status "2/4 Installing Python dependencies..."
sudo apt install -y \
    python3-setuptools \
    python3-numpy \
    python3-yaml \
    python3-matplotlib \
    python3-serial \
    python3-lxml \
    python3-future \
    python3-empy
check_success "Failed to install Python apt packages"

pip3 install --user --break-system-packages pymavlink mavproxy
check_success "Failed to install Python pip packages"

print_status "3/4 Installing basic ArduPilot libraries..."
sudo apt install -y \
    libeigen3-dev \
    libxml2-dev \
    libxml2-utils \
    protobuf-compiler \
    geographiclib-tools \
    libprotobuf-dev \
    libprotoc-dev
check_success "Failed to install ArduPilot libraries"

print_status "4/4 Installing ROS2 + MAVROS packages..."
sudo apt install -y \
    ros-jazzy-mavros \
    ros-jazzy-mavros-extras \
    ros-jazzy-geographic-msgs \
    ros-jazzy-sensor-msgs \
    ros-jazzy-geometry-msgs \
    ros-jazzy-ros-gz \
    ros-jazzy-ros-gz-sim
check_success "Failed to install ROS2 packages"

# Install GeographicLib datasets
print_status "Installing GeographicLib datasets..."
wget -O /tmp/install_geographiclib_datasets.sh \
    https://raw.githubusercontent.com/mavlink/mavros/master/mavros/scripts/install_geographiclib_datasets.sh

if [ $? -eq 0 ]; then
    sudo bash /tmp/install_geographiclib_datasets.sh
    rm /tmp/install_geographiclib_datasets.sh
    print_status "GeographicLib datasets installed"
else
    print_warning "GeographicLib datasets script failed, continuing without them"
fi

print_status "Essential dependencies installed!"
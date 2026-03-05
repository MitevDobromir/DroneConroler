#!/bin/bash
# test_sensors.sh — Verify camera and sonar sensors are publishing
# Run this after spawning iris_camera_sonar and opening the Gazebo GUI

echo "============================================"
echo "  Sensor Test — iris_camera_sonar"
echo "============================================"
echo ""

# Find all drone sensor topics
echo "--- All drone topics ---"
gz topic -l | grep "drone/" | sort
echo ""

# Test each sonar — print one reading from each
echo "--- Sonar Front (5s sample) ---"
timeout 5 gz topic -e -t /drone/sonar/front -n 1 2>/dev/null
echo ""

echo "--- Sonar Left (5s sample) ---"
timeout 5 gz topic -e -t /drone/sonar/left -n 1 2>/dev/null
echo ""

echo "--- Sonar Right (5s sample) ---"
timeout 5 gz topic -e -t /drone/sonar/right -n 1 2>/dev/null
echo ""

echo "--- Sonar Down (5s sample) ---"
timeout 5 gz topic -e -t /drone/sonar/down -n 1 2>/dev/null
echo ""

# Check camera topic
echo "--- Camera topic ---"
CAMERA_TOPIC=$(gz topic -l | grep "drone/camera" | head -1)
if [ -n "$CAMERA_TOPIC" ]; then
    echo "Camera publishing on: $CAMERA_TOPIC"
else
    echo "WARNING: No camera topic found — is the Gazebo GUI running?"
fi
echo ""

# Check streaming enable topic
echo "--- Camera streaming ---"
STREAM_TOPIC=$(gz topic -l | grep "enable_streaming" | head -1)
if [ -n "$STREAM_TOPIC" ]; then
    echo "Enable streaming with:"
    echo "  gz topic -t $STREAM_TOPIC -m gz.msgs.Boolean -p 'data: 1'"
    echo ""
    echo "View feed with:"
    echo "  gst-launch-1.0 -v udpsrc port=5600 caps='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264' ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false"
else
    echo "WARNING: No streaming topic found — camera may not be loaded"
fi
echo ""
echo "============================================"
echo "  If sonar topics show 'inf' = no obstacle"
echo "  If sonar topics show a number = distance"
echo "============================================"

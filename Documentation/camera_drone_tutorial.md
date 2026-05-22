# Camera Drone Tutorial — Iris with Gimbal

Step-by-step guide to flying the camera-equipped Iris drone with live video feed.

Requires 4 terminals. Open them all before starting.

---

## Terminal 1 — Gazebo Server

Start the headless physics server:

```bash
source ~/ROS2_Tools/ArduPilot/setup_ardupilot_env.sh
export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH:~/ROS2_Tools/Models:~/ROS2_Tools/Worlds
gz sim -s -r -v4 ~/ROS2_Tools/Worlds/plains_env.sdf
```

Wait until you see:
```
World [plains_world] initialized with [1ms] physics profile.
```

---

## Terminal 2 — Gazebo GUI

The camera sensor needs the rendering engine to produce images.
Open the GUI window (connects to the running server):

```bash
gz sim -g
```

You should see the Gazebo 3D window with the green ground plane.
Leave this running — the camera won't work without it.

---

## Terminal 3 — Spawn the Camera Drone

Spawn `iris_with_gimbal` (not `iris_with_ardupilot`):

```bash
gz service -s /world/plains_world/create \
    --reqtype gz.msgs.EntityFactory \
    --reptype gz.msgs.Boolean \
    --timeout 3000 \
    --req 'sdf_filename: "/home/vboxuser/ROS2_Tools/ArduPilot/ardupilot_gazebo/models/iris_with_gimbal/model.sdf", name: "iris_with_gimbal_1", pose: {position: {x: 0, y: 0, z: 0.5}}'
```

You should see the drone appear in the Gazebo GUI window.

---

## Terminal 3 — Start ArduCopter SITL

In the same terminal (after spawn completes), start ArduCopter with gimbal params:

```bash
cd ~/ROS2_Tools/ArduPilot/ardupilot/Tools/autotest

~/ROS2_Tools/ArduPilot/ardupilot/build/sitl/bin/arducopter \
    --model JSON \
    --speedup 1 \
    --defaults default_params/copter.parm,default_params/gazebo-iris.parm,~/ROS2_Tools/ArduPilot/ardupilot_gazebo/config/gazebo-iris-gimbal.parm \
    --sim-address=127.0.0.1 \
    -I0
```

Wait until you see:
```
bind port 5760 for SERIAL0
Waiting for connection ....
```

---

## Terminal 4 — Start MAVProxy

```bash
mavproxy.py --master tcp:127.0.0.1:5760 --out 127.0.0.1:14550
```

Wait until you see:
```
AP: ArduPilot Ready
```

---

## Terminal 4 — Enable Camera Stream

First, find the exact camera topic:

```bash
gz topic -l | grep enable_streaming
```

It will show something like:
```
/world/plains_world/model/iris_with_gimbal_1/model/gimbal/link/pitch_link/sensor/camera/image/enable_streaming
```

Enable it (paste YOUR topic from above):

```bash
gz topic -t /world/plains_world/model/iris_with_gimbal_1/model/gimbal/link/pitch_link/sensor/camera/image/enable_streaming -m gz.msgs.Boolean -p "data: 1"
```

---

## Terminal 4 — View Camera Feed

```bash
gst-launch-1.0 -v udpsrc port=5600 \
    caps='application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264' \
    ! rtph264depay ! avdec_h264 ! videoconvert ! autovideosink sync=false
```

A video window should open showing the drone's camera view (pointing down at the ground).

---

## Fly the Drone

Back in the MAVProxy terminal (Terminal 4), open a second window or use another terminal:

```bash
mavproxy.py --master tcp:127.0.0.1:5760 --out 127.0.0.1:14550
```

Then in MAVProxy:

```
mode guided
arm throttle
takeoff 10
```

Watch the camera feed window — you should see the ground moving away as the drone climbs.

---

## Control the Gimbal

In MAVProxy, the gimbal is controlled via RC channels:
- Channel 6: Gimbal yaw
- Channel 7: Gimbal roll  
- Channel 8: Gimbal pitch

Example — tilt camera down:
```
rc 8 1200
```

Example — tilt camera forward:
```
rc 8 1800
```

Example — center gimbal:
```
rc 8 1500
```

---

## Troubleshooting

**No video window appears:**
- The Gazebo GUI (Terminal 2) must be running — the camera needs the rendering engine
- Check if the pipeline says "PLAYING" — the window might be behind other windows

**Pipeline hangs at "Setting pipeline to PAUSED":**
- Camera streaming wasn't enabled — run the gz topic enable command again
- Wrong topic name — double-check with `gz topic -l | grep enable_streaming`

**"No such model" on spawn:**
- Check the model path exists:
  ```bash
  ls ~/ROS2_Tools/ArduPilot/ardupilot_gazebo/models/iris_with_gimbal/model.sdf
  ```

**ArduCopter won't arm ("Accels inconsistent"):**
- Normal on first start — wait 10 seconds and try again
- The EKF needs time to converge

**Camera shows black/nothing:**
- Make sure Gazebo GUI is open and rendering
- Try: `gz sim -g` if the GUI closed

---

## Cleanup

When done, stop everything in reverse order:

```bash
# Stop GStreamer: Ctrl+C in Terminal 4
# Stop MAVProxy: Ctrl+C
# Stop ArduCopter: Ctrl+C in Terminal 3
# Stop Gazebo GUI: Ctrl+C in Terminal 2
# Stop Gazebo server: Ctrl+C in Terminal 1
```

Or kill everything at once:
```bash
pkill -f "gz sim" && pkill -f arducopter && pkill -f mavproxy && pkill -f gst-launch
```

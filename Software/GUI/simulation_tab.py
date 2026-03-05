"""
simulation_tab.py - Tab for launching pre-configured simulation scenarios

Scans ~/ROS2_Tools/Simulations/ for .simulation files (JSON).
Each file defines a complete simulation: environment, drone, SITL driver,
and a flight plan.

File format (.simulation):
{
    "name": "My Simulation",
    "description": "What this scenario does.",
    "environment": {
        "world_file": "plains_env.sdf",
        "world_name": "plains_world"
    },
    "drone": {
        "model_path": "$ARDUPILOT_GAZEBO/models/iris_with_ardupilot/model.sdf",
        "spawn_name": "iris_drone",
        "spawn_position": [0, 0, 0.5]
    },
    "driver": {
        "binary": "$ARDUPILOT_HOME/build/sitl/bin/arducopter",
        "defaults": "default_params/copter.parm,default_params/gazebo-iris.parm",
        "working_dir": "$ARDUPILOT_HOME/Tools/autotest"
    },
    "flight_plan": [
        {"type": "takeoff", "altitude": 10},
        {"type": "move", "x": 5, "y": 0, "speed": 1.0},
        {"type": "land"}
    ]
}
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import os
import signal
import socket
import threading
import time
import json
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

from .global_state import GlobalState
from .theme import get_terminal_colors, COLORS

# Try to import flight controller for automated missions
try:
    import sys as _sys
    _sys.path.insert(0, str(Path.home() / "ROS2_Tools" / "Software" / "Common"))
    from flight_controller import DroneController
    FLIGHT_CONTROLLER_AVAILABLE = True
except ImportError:
    FLIGHT_CONTROLLER_AVAILABLE = False


class SimulationTab(ttk.Frame):
    """Tab for launching pre-configured simulation environments"""

    PHASE_IDLE = 'idle'
    PHASE_ENV = 'Launching Environment'
    PHASE_SPAWN = 'Spawning Drone'
    PHASE_DRIVER = 'Starting Driver'
    PHASE_CONNECT = 'Connecting MAVLink'
    PHASE_MISSION = 'Running Mission'
    PHASE_DONE = 'Ready'
    PHASE_ERROR = 'Error'

    def __init__(self, parent, state: GlobalState):
        super().__init__(parent, padding="10")
        self.state = state

        # Paths
        self.ardupilot_home = state.ros2_tools_path / "ArduPilot" / "ardupilot"
        self.ardupilot_gazebo = state.ros2_tools_path / "ArduPilot" / "ardupilot_gazebo"
        self.worlds_path = state.ros2_tools_path / "Worlds"
        self.simulations_dir = state.ros2_tools_path / "Simulations"

        # Ensure simulations directory exists
        self.simulations_dir.mkdir(parents=True, exist_ok=True)

        # Runtime state
        self.simulations: List[Dict] = []   # Each entry has an extra '_path' key
        self.is_running = False
        self.abort_requested = False
        self.gazebo_process: Optional[subprocess.Popen] = None
        self.gui_process: Optional[subprocess.Popen] = None
        self.arducopter_process: Optional[subprocess.Popen] = None
        self.mavproxy_process: Optional[subprocess.Popen] = None
        self.drone_controller: Optional[object] = None
        self.current_phase = self.PHASE_IDLE

        self.setup_gui()
        self.scan_simulations()

    # ================================================================== GUI
    def setup_gui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(1, weight=1)

        # ── Status bar ──
        status_frame = ttk.Frame(self)
        status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT)
        self.phase_var = tk.StringVar(value="Idle")
        self.phase_label = ttk.Label(status_frame, textvariable=self.phase_var,
                                     style='StatusGray.TLabel')
        self.phase_label.pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(status_frame, text="Step:").pack(side=tk.LEFT)
        self.step_var = tk.StringVar(value="—")
        ttk.Label(status_frame, textvariable=self.step_var,
                  style='Status.TLabel').pack(side=tk.LEFT, padx=(5, 0))

        # ── Left panel – Simulation list ──
        left_frame = ttk.LabelFrame(self, text="Simulations", padding="10")
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.sim_listbox = tk.Listbox(
            list_frame, font=('Consolas', 10),
            selectmode=tk.SINGLE, exportselection=False)
        self.sim_listbox.grid(row=0, column=0, sticky="nsew")
        self.sim_listbox.bind('<<ListboxSelect>>', self.on_sim_selected)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=self.sim_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.sim_listbox.config(yscrollcommand=scrollbar.set)

        # Buttons under list
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        ttk.Button(btn_frame, text="Refresh",
                   command=self.scan_simulations).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ttk.Button(btn_frame, text="+ New",
                   command=self.open_add_dialog).grid(row=0, column=1, sticky="ew", padx=2)
        self.remove_btn = ttk.Button(btn_frame, text="Delete",
                                     command=self.remove_simulation, state='disabled')
        self.remove_btn.grid(row=0, column=2, sticky="ew", padx=(2, 0))

        # ── Right panel ──
        right_frame = ttk.Frame(self)
        right_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(2, weight=1)

        # Details
        details_frame = ttk.LabelFrame(right_frame, text="Details", padding="10")
        details_frame.grid(row=0, column=0, sticky="ew")
        details_frame.columnconfigure(1, weight=1)

        ttk.Label(details_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=2)
        self.detail_name_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_name_var,
                  font=('Segoe UI', 10, 'bold')).grid(row=0, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="File:").grid(row=1, column=0, sticky="w", pady=2)
        self.detail_file_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_file_var,
                  font=('Consolas', 9)).grid(row=1, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="World:").grid(row=2, column=0, sticky="w", pady=2)
        self.detail_world_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_world_var,
                  font=('Consolas', 9)).grid(row=2, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="Drone:").grid(row=3, column=0, sticky="w", pady=2)
        self.detail_drone_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_drone_var,
                  font=('Consolas', 9)).grid(row=3, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="Position:").grid(row=4, column=0, sticky="w", pady=2)
        self.detail_pos_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_pos_var,
                  font=('Consolas', 9)).grid(row=4, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="Info:").grid(row=5, column=0, sticky="nw", pady=2)
        self.detail_desc_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_desc_var,
                  wraplength=400, justify=tk.LEFT).grid(
            row=5, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="Plan:").grid(row=6, column=0, sticky="nw", pady=2)
        self.detail_plan_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_plan_var,
                  font=('Consolas', 9), wraplength=400,
                  justify=tk.LEFT).grid(row=6, column=1, sticky="w", padx=(10, 0))

        # Controls
        ctrl_frame = ttk.LabelFrame(right_frame, text="Controls", padding="10")
        ctrl_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=1)
        ctrl_frame.columnconfigure(2, weight=1)

        self.run_btn = ttk.Button(
            ctrl_frame, text="▶  Launch",
            command=self.run_simulation, state='disabled',
            style='Accent.TButton')
        self.run_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=5)

        self.abort_btn = ttk.Button(
            ctrl_frame, text="⏹  Abort",
            command=self.abort_simulation, state='disabled',
            style='Danger.TButton')
        self.abort_btn.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        self.stop_btn = ttk.Button(
            ctrl_frame, text="⏹  Stop Gazebo",
            command=self.stop_gazebo, state='disabled')
        self.stop_btn.grid(row=0, column=2, sticky="ew", padx=(5, 0), pady=5)

        # Progress
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            ctrl_frame, variable=self.progress_var,
            maximum=100, mode='determinate')
        self.progress_bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 0))

        # Terminal output
        term_frame = ttk.LabelFrame(right_frame, text="Simulation Log", padding="10")
        term_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        term_frame.columnconfigure(0, weight=1)
        term_frame.rowconfigure(0, weight=1)

        tc = get_terminal_colors()
        self.terminal_text = scrolledtext.ScrolledText(
            term_frame, height=14, font=('Consolas', 9),
            state='disabled',
            bg=tc['bg'], fg=tc['fg'],
            selectbackground=tc['select_bg'],
            selectforeground=tc['select_fg'],
            insertbackground=tc['fg'],
            relief='flat', borderwidth=0)
        self.terminal_text.grid(row=0, column=0, sticky="nsew")

        ttk.Button(term_frame, text="Clear Log",
                   command=self.clear_log).grid(row=1, column=0, sticky="e", pady=(5, 0))

    # ======================================================= Scan directory
    def scan_simulations(self):
        """Scan the Simulations directory for .simulation files"""
        self.simulations.clear()
        self.sim_listbox.delete(0, tk.END)

        if not self.simulations_dir.exists():
            self.log(f"[WARN] Simulations directory not found: {self.simulations_dir}")
            return

        sim_files = sorted(self.simulations_dir.glob("*.simulation"))

        for sim_file in sim_files:
            try:
                with open(sim_file, 'r') as f:
                    data = json.load(f)

                # Validate required fields
                if not all(k in data for k in ('name', 'environment', 'drone', 'driver', 'flight_plan')):
                    self.log(f"[WARN] Skipping {sim_file.name}: missing required fields "
                             f"(need: name, environment, drone, driver, flight_plan)")
                    continue

                if 'world_file' not in data['environment']:
                    self.log(f"[WARN] Skipping {sim_file.name}: environment needs world_file")
                    continue

                if not all(k in data['drone'] for k in ('model_path', 'spawn_name')):
                    self.log(f"[WARN] Skipping {sim_file.name}: drone needs model_path and spawn_name")
                    continue

                # Store with file path reference
                data['_path'] = sim_file
                self.simulations.append(data)
                self.sim_listbox.insert(tk.END, data['name'])

            except json.JSONDecodeError as e:
                self.log(f"[WARN] Skipping {sim_file.name}: invalid JSON — {e}")
            except Exception as e:
                self.log(f"[WARN] Skipping {sim_file.name}: {e}")

        self.log(f"[INFO] Found {len(self.simulations)} simulation(s) in {self.simulations_dir}")

    # ========================================================== Selection
    def on_sim_selected(self, event=None):
        sel = self.sim_listbox.curselection()
        if not sel:
            return
        sim = self.simulations[sel[0]]

        self.detail_name_var.set(sim['name'])
        self.detail_file_var.set(sim['_path'].name)
        self.detail_world_var.set(sim['environment']['world_file'])
        self.detail_drone_var.set(sim['drone']['spawn_name'])
        pos = sim['drone'].get('spawn_position', [0, 0, 0.5])
        self.detail_pos_var.set(f"X={pos[0]}  Y={pos[1]}  Z={pos[2]}")
        self.detail_desc_var.set(sim.get('description', ''))

        # Format flight plan
        steps = []
        for s in sim.get('flight_plan', []):
            if s['type'] == 'takeoff':
                steps.append(f"Takeoff {s['altitude']}m")
            elif s['type'] == 'move':
                steps.append(f"Move X={s['x']} Y={s['y']} @ {s.get('speed', 1)}m/s")
            elif s['type'] == 'land':
                steps.append("Land")
        self.detail_plan_var.set(" → ".join(steps) if steps else "—")

        self.remove_btn.config(state='normal')
        self.run_btn.config(state='normal' if not self.is_running else 'disabled')

    # ====================================================== Path helpers
    def _resolve(self, raw: str) -> str:
        resolved = raw.replace('$ARDUPILOT_HOME', str(self.ardupilot_home))
        resolved = resolved.replace('$ARDUPILOT_GAZEBO', str(self.ardupilot_gazebo))
        resolved = os.path.expanduser(resolved)
        resolved = os.path.expandvars(resolved)
        return resolved

    def _parse_world_name(self, sdf_path: Path) -> Optional[str]:
        try:
            tree = ET.parse(sdf_path)
            root = tree.getroot()
            w = root.find('.//world')
            if w is not None:
                return w.get('name')
        except Exception:
            pass
        return None

    # ====================================================== Run / Abort / Stop
    def run_simulation(self):
        sel = self.sim_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a simulation first")
            return
        if self.is_running:
            messagebox.showwarning("Running", "A simulation is already running")
            return
        if self.state.is_gazebo_running:
            messagebox.showwarning("Gazebo Running",
                                   "Gazebo is already running.\nStop it first from the "
                                   "Environment tab or click 'Stop Gazebo'.")
            return

        sim = self.simulations[sel[0]]
        self.abort_requested = False
        self.is_running = True
        self.run_btn.config(state='disabled')
        self.abort_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.progress_var.set(0)

        thread = threading.Thread(target=self._execute_simulation, args=(sim,), daemon=True)
        thread.start()

    def abort_simulation(self):
        if not self.is_running:
            return
        self.abort_requested = True
        self.log("\n[ABORT] Abort requested — cleaning up...")
        self._set_phase('Aborting')

    def stop_gazebo(self):
        """Stop Gazebo server"""
        self._stop_all_processes()
        self.log("[STOP] Gazebo stopped")
        self._set_phase(self.PHASE_IDLE)
        self._set_step("—")
        self.progress_var.set(0)
        self.after(0, lambda: self.stop_btn.config(state='disabled'))

    # ====================================================== Orchestrator
    def _execute_simulation(self, sim: Dict):
        """Main orchestration — env → spawn → driver → connect → flight plan."""
        flight_plan = sim['flight_plan']
        total_steps = 4 + len(flight_plan)  # env + spawn + driver + connect + steps

        try:
            self.log(f"\n{'=' * 50}")
            self.log(f"  SIMULATION: {sim['name']}")
            self.log(f"  File: {sim['_path'].name}")
            self.log(f"{'=' * 50}\n")

            # ── Phase 1: Launch Environment ──
            self._set_phase(self.PHASE_ENV)
            self._set_step("Launching Gazebo server")
            self._update_progress(0, total_steps)

            if not self._launch_environment(sim['environment']):
                return

            if self.abort_requested:
                self._stop_all_processes()
                return

            # ── Phase 2: Spawn Drone ──
            self._set_phase(self.PHASE_SPAWN)
            self._set_step("Spawning drone")
            self._update_progress(1, total_steps)

            world_name = sim['environment'].get('world_name', 'default')
            if not self._spawn_drone(sim['drone'], world_name):
                return

            if self.abort_requested:
                self._stop_all_processes()
                return

            # ── Launch GUI (best-effort, non-blocking) ──
            self._set_step("Opening Gazebo window")
            self._launch_gui()

            # ── Phase 3: Start SITL Driver ──
            self._set_phase(self.PHASE_DRIVER)
            self._set_step("Starting ArduCopter + MAVProxy")
            self._update_progress(2, total_steps)

            if not self._start_driver(sim['driver']):
                return

            if self.abort_requested:
                self._stop_all_processes()
                return

            # ── Phase 4: Connect MAVLink ──
            self._set_phase(self.PHASE_CONNECT)
            self._set_step("Connecting to drone")
            self._update_progress(3, total_steps)

            if not self._connect_mavlink():
                return

            if self.abort_requested:
                self._emergency_land()
                self._stop_all_processes()
                return

            # ── Phase 5: Execute Flight Plan ──
            self._set_phase(self.PHASE_MISSION)

            if not self._execute_flight_plan(flight_plan, 4, total_steps):
                return

            # ── Done ──
            self._update_progress(total_steps, total_steps)
            self._set_phase(self.PHASE_DONE)
            self._set_step("Mission complete")

            self.log(f"\n{'=' * 50}")
            self.log(f"  SIMULATION COMPLETE")
            self.log(f"{'=' * 50}")
            self.log(f"\nGazebo still running — click 'Stop Gazebo' when finished.")

        except Exception as e:
            self.log(f"\n[ERROR] Simulation failed: {e}")
            self._set_phase(self.PHASE_ERROR)
            self._emergency_land()
            self._stop_all_processes()
        finally:
            self.is_running = False
            self.abort_requested = False
            self.drone_controller = None

            # Always clean up SITL if still running
            self._stop_sitl_processes()

            def _update_buttons():
                self.run_btn.config(
                    state='normal' if self.sim_listbox.curselection() else 'disabled')
                self.abort_btn.config(state='disabled')
                # If Gazebo is still running, enable stop button
                if self.gazebo_process and self.gazebo_process.poll() is None:
                    self.stop_btn.config(state='normal')
                else:
                    self.stop_btn.config(state='disabled')
            self.after(0, _update_buttons)

    # ─────────────────────────────────── Phase 1: Environment
    def _launch_environment(self, env_cfg: Dict) -> bool:
        world_file = env_cfg['world_file']
        world_name = env_cfg.get('world_name')

        self.log(f"[ENV] Launching {world_file}...")

        # Check world file exists
        world_path = self.worlds_path / world_file
        if not world_path.exists():
            self.log(f"[ERROR] World file not found: {world_path}")
            self._set_phase(self.PHASE_ERROR)
            return False

        # Parse world name from SDF if not provided
        if not world_name:
            world_name = self._parse_world_name(world_path) or 'default'
            env_cfg['world_name'] = world_name

        # Update global state
        self.state.set_world(world_name, world_file)
        self.state.clear_drones()

        # Launch Gazebo in SERVER-ONLY mode (`gz sim -s -r`).
        # This avoids the GUI process entirely, which crashes on
        # Ubuntu 24.04 VirtualBox due to snap's broken libpthread.
        setup_ardupilot = self.state.ros2_tools_path / "ArduPilot" / "setup_ardupilot_env.sh"
        ros2_tools = self.state.ros2_tools_path

        env_setup = 'source /opt/ros/jazzy/setup.bash && '
        if setup_ardupilot.exists():
            env_setup += f'source {setup_ardupilot} && '

        env_setup += (
            f'export GZ_SIM_RESOURCE_PATH='
            f'"$GZ_SIM_RESOURCE_PATH:{ros2_tools}/Models:{ros2_tools}/Worlds" && '
        )

        gz_cmd = f'gz sim -s -r -v4 {world_path}'
        full_cmd = f'{env_setup}{gz_cmd}'

        self.log("[ENV] Starting Gazebo server (headless)")
        self.gazebo_process = subprocess.Popen(
            ['bash', '-c', full_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid
        )
        self.state.gazebo_process = self.gazebo_process
        self.state.set_gazebo_running(True)

        # Stream output to log
        def _read_output():
            try:
                for line in iter(self.gazebo_process.stdout.readline, ''):
                    if line.strip():
                        self.after(0, lambda l=line: self.log(f"[GZ] {l.rstrip()}"))
            except Exception:
                pass
        threading.Thread(target=_read_output, daemon=True).start()

        # Wait for Gazebo to be ready
        self.log("[ENV] Waiting for Gazebo to initialize...")
        ready = False
        for i in range(60):
            if self.abort_requested:
                return False
            if self.gazebo_process.poll() is not None:
                self.log("[ERROR] Gazebo process exited unexpectedly")
                self._set_phase(self.PHASE_ERROR)
                return False
            try:
                result = subprocess.run(
                    ['gz', 'topic', '-l'],
                    capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0 and result.stdout.strip():
                    ready = True
                    break
            except Exception:
                pass
            time.sleep(1)
            if i % 5 == 0 and i > 0:
                self.log(f"[ENV] Still waiting... ({i}s)")

        if not ready:
            self.log("[ERROR] Gazebo failed to start within 60 seconds")
            self._set_phase(self.PHASE_ERROR)
            return False

        self.log("[ENV] Gazebo server running — settling for 5 seconds...")
        time.sleep(5)
        self.log("[ENV] Environment ready")
        return True

    # ─────────────────────────────────── Phase 2: Spawn Drone
    def _spawn_drone(self, drone_cfg: Dict, world_name: str) -> bool:
        model_path = self._resolve(drone_cfg['model_path'])
        spawn_name = drone_cfg['spawn_name']
        x, y, z = drone_cfg.get('spawn_position', [0, 0, 0.5])

        self.log(f"[SPAWN] Spawning {spawn_name} at ({x}, {y}, {z})...")

        if not Path(model_path).exists():
            self.log(f"[ERROR] Drone model not found: {model_path}")
            self._set_phase(self.PHASE_ERROR)
            return False

        cmd = [
            'gz', 'service',
            '-s', f'/world/{world_name}/create',
            '--reqtype', 'gz.msgs.EntityFactory',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '3000',
            '--req', (
                f'sdf_filename: "{model_path}", '
                f'name: "{spawn_name}", '
                f'pose: {{position: {{x: {x}, y: {y}, z: {z}}}}}'
            )
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                self.log(f"[SPAWN] {spawn_name} spawned successfully")
                self.state.add_drone({
                    'name': spawn_name,
                    'model': drone_cfg['model_path'],
                    'position': (x, y, z)
                })
                time.sleep(2)  # Let physics settle
                return True
            else:
                self.log(f"[ERROR] Spawn failed: {result.stderr or result.stdout}")
                self._set_phase(self.PHASE_ERROR)
                return False
        except subprocess.TimeoutExpired:
            self.log("[ERROR] Spawn command timed out")
            self._set_phase(self.PHASE_ERROR)
            return False

    # ─────────────────────────────────── GUI window (optional)
    def _launch_gui(self):
        """Launch the Gazebo GUI window as a separate process.

        The GUI connects to the already-running server via `gz sim -g`.
        If it crashes (e.g. snap libpthread conflict on VirtualBox), the
        server keeps running — no harm done.
        """
        self.log("[GUI] Launching Gazebo GUI window...")

        # Build environment that filters out snap paths from LD_LIBRARY_PATH
        # to work around the libpthread symbol conflict on Ubuntu 24.04 + VirtualBox.
        setup_ardupilot = self.state.ros2_tools_path / "ArduPilot" / "setup_ardupilot_env.sh"

        env_setup = 'source /opt/ros/jazzy/setup.bash && '
        if setup_ardupilot.exists():
            env_setup += f'source {setup_ardupilot} && '

        # Strip snap paths from LD_LIBRARY_PATH
        env_setup += (
            'export LD_LIBRARY_PATH='
            '$(echo "$LD_LIBRARY_PATH" | tr \':\' \'\\n\' | grep -v \'/snap/\' '
            '| tr \'\\n\' \':\' | sed \'s/:$//\') && '
        )

        gui_cmd = f'{env_setup}gz sim -g -v4'

        try:
            self.gui_process = subprocess.Popen(
                ['bash', '-c', gui_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=os.setsid
            )

            # Monitor GUI output in background
            def _read_gui():
                try:
                    for line in iter(self.gui_process.stdout.readline, ''):
                        if line.strip():
                            self.after(0, lambda l=line: self.log(f"[GUI] {l.rstrip()}"))
                except Exception:
                    pass
                # Check if it exited quickly (crash)
                if self.gui_process and self.gui_process.poll() is not None:
                    rc = self.gui_process.returncode
                    if rc != 0:
                        self.after(0, lambda: self.log(
                            f"[GUI] Window closed (exit code {rc}) — "
                            f"server still running, this is OK"))
            threading.Thread(target=_read_gui, daemon=True).start()

            # Give it a moment to either start or crash
            time.sleep(3)

            if self.gui_process.poll() is None:
                self.log("[GUI] Gazebo GUI window is open")
            else:
                self.log("[GUI] GUI window failed to start — server still running headless")
                self.log("[GUI] This is normal on VirtualBox due to snap library conflicts")
                self.gui_process = None

        except Exception as e:
            self.log(f"[GUI] Could not launch GUI: {e}")
            self.log("[GUI] Server continues running headless")
            self.gui_process = None

    # ─────────────────────────────────── Phase 3: Start SITL Driver
    def _start_driver(self, driver_cfg: Dict) -> bool:
        """Launch arducopter + mavproxy directly (no gnome-terminal)."""
        binary = self._resolve(driver_cfg.get(
            'binary', '$ARDUPILOT_HOME/build/sitl/bin/arducopter'))
        defaults = driver_cfg.get(
            'defaults', 'default_params/copter.parm,default_params/gazebo-iris.parm')
        work_dir = self._resolve(driver_cfg.get('working_dir', ''))
        if not work_dir or not Path(work_dir).is_dir():
            work_dir = str(Path.home())

        # Verify binary exists
        if not Path(binary).exists():
            self.log(f"[ERROR] ArduCopter binary not found: {binary}")
            self.log("[HINT]  Build it with:")
            self.log(f"        cd {self.ardupilot_home} && ./waf configure --board sitl && ./waf copter")
            self._set_phase(self.PHASE_ERROR)
            return False

        # Step 1: Launch ArduCopter
        ardu_cmd = (
            f'{binary} '
            f'--model JSON '
            f'--speedup 1 '
            f'--defaults {defaults} '
            f'--sim-address=127.0.0.1 '
            f'-I0'
        )
        self.log(f"[DRIVER] Launching ArduCopter directly (no gnome-terminal)")
        self.log(f"[DRIVER] Binary: {binary}")
        self.log(f"[DRIVER] Working dir: {work_dir}")

        self.arducopter_process = subprocess.Popen(
            ['bash', '-c', ardu_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=work_dir,
            preexec_fn=os.setsid,
        )

        def _read_ardu():
            try:
                for line in iter(self.arducopter_process.stdout.readline, ''):
                    if line.strip():
                        self.after(0, lambda l=line: self.log(f"[ARDU] {l.rstrip()}"))
            except Exception:
                pass
        threading.Thread(target=_read_ardu, daemon=True).start()

        # Step 2: Wait for TCP 5760
        self.log("[DRIVER] Waiting for ArduCopter to open TCP 5760...")
        tcp_ready = False
        for i in range(60):
            if self.abort_requested:
                return False
            if self.arducopter_process.poll() is not None:
                self.log("[ERROR] ArduCopter process exited unexpectedly")
                self._set_phase(self.PHASE_ERROR)
                return False
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', 5760))
                sock.close()
                if result == 0:
                    tcp_ready = True
                    break
            except Exception:
                pass
            time.sleep(1)
            if i % 10 == 0 and i > 0:
                self.log(f"[DRIVER] ArduCopter starting... ({i}s)")

        if not tcp_ready:
            self.log("[ERROR] ArduCopter failed to open TCP 5760 within 60s")
            self._set_phase(self.PHASE_ERROR)
            return False

        self.log("[DRIVER] ArduCopter TCP 5760 ready")

        # Step 3: Launch MAVProxy
        mavproxy_cmd = (
            'mavproxy.py '
            '--master tcp:127.0.0.1:5760 '
            '--out 127.0.0.1:14550 '
            '--sitl 127.0.0.1:5501 '
            '--daemon'
        )
        self.log("[DRIVER] Launching MAVProxy...")

        self.mavproxy_process = subprocess.Popen(
            ['bash', '-c', mavproxy_cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid,
        )

        def _read_mav():
            try:
                for line in iter(self.mavproxy_process.stdout.readline, ''):
                    if line.strip():
                        self.after(0, lambda l=line: self.log(f"[MAV] {l.rstrip()}"))
            except Exception:
                pass
        threading.Thread(target=_read_mav, daemon=True).start()

        # Step 4: Wait for UDP 14550
        self.log("[DRIVER] Waiting for MAVProxy to forward on UDP 14550...")
        udp_ready = False
        for i in range(60):
            if self.abort_requested:
                return False
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(1)
                sock.bind(('127.0.0.1', 14550))
                sock.close()
                # If we CAN bind, MAVProxy hasn't started forwarding yet
            except OSError:
                # Port in use = MAVProxy is sending data = ready
                udp_ready = True
                break
            except Exception:
                pass
            time.sleep(1)
            if i % 5 == 0 and i > 0:
                self.log(f"[DRIVER] MAVProxy connecting... ({i}s)")

        if not udp_ready:
            self.log("[WARN] MAVProxy UDP 14550 not detected within 60s")
            self.log("[DRIVER] Proceeding anyway — MAVProxy may still be initializing")

        self.log("[DRIVER] SITL driver started")
        time.sleep(2)
        return True

    # ─────────────────────────────────── Phase 4: Connect MAVLink
    def _connect_mavlink(self) -> bool:
        if not FLIGHT_CONTROLLER_AVAILABLE:
            self.log("[ERROR] flight_controller.py not found in Software/Common/")
            self._set_phase(self.PHASE_ERROR)
            return False

        self.log("[CONNECT] Connecting to drone via MAVLink...")
        try:
            self.drone_controller = DroneController()
        except Exception as e:
            self.log(f"[ERROR] MAVLink connection failed: {e}")
            self._set_phase(self.PHASE_ERROR)
            return False

        self.log("[CONNECT] Waiting for GPS lock...")
        if not self.drone_controller.wait_for_gps():
            self.log("[ERROR] GPS lock timeout")
            self._set_phase(self.PHASE_ERROR)
            return False

        self.log("[CONNECT] Setting GUIDED mode...")
        if not self.drone_controller.set_mode('GUIDED'):
            self.log("[ERROR] Failed to set GUIDED mode")
            self._set_phase(self.PHASE_ERROR)
            return False

        self.log("[CONNECT] Arming motors...")
        if not self.drone_controller.arm():
            self.log("[ERROR] Arming failed")
            self._set_phase(self.PHASE_ERROR)
            return False

        self.log("[CONNECT] Armed and ready\n")
        return True

    # ─────────────────────────────────── Phase 5: Execute Flight Plan
    def _execute_flight_plan(self, plan: List[Dict],
                             step_offset: int, total_steps: int) -> bool:
        dc = self.drone_controller
        if not dc:
            self.log("[ERROR] No drone controller")
            return False

        for i, step in enumerate(plan):
            if self.abort_requested:
                self._emergency_land()
                return False

            step_type = step['type']
            step_num = i + 1
            self._update_progress(step_offset + i, total_steps)

            if step_type == 'takeoff':
                alt = step['altitude']
                self.log(f"[STEP {step_num}/{len(plan)}] Takeoff to {alt}m")
                self._set_step(f"Takeoff {alt}m")
                if not dc.takeoff(alt):
                    self.log("[ERROR] Takeoff failed")
                    self._emergency_land()
                    return False

            elif step_type == 'move':
                x, y = step['x'], step['y']
                speed = step.get('speed', 1.0)
                self.log(f"[STEP {step_num}/{len(plan)}] Move X={x}m Y={y}m @ {speed}m/s")
                self._set_step(f"Move X={x} Y={y}")
                if not dc.move_relative(x, y, speed):
                    self.log("[ERROR] Move failed")
                    self._emergency_land()
                    return False

            elif step_type == 'land':
                self.log(f"[STEP {step_num}/{len(plan)}] Landing")
                self._set_step("Landing")
                dc.land()

            self.log(f"  Done\n")
            time.sleep(1)

        return True

    def _emergency_land(self):
        """Emergency land if something goes wrong during automated flight"""
        if self.drone_controller:
            try:
                self.log("[SAFETY] Emergency landing...")
                self.drone_controller.land()
            except Exception:
                pass

    # ====================================================== Process management
    def _stop_sitl_processes(self):
        """Stop ArduCopter + MAVProxy only — Gazebo keeps running."""
        had_processes = self.mavproxy_process or self.arducopter_process

        if self.mavproxy_process:
            try:
                os.killpg(os.getpgid(self.mavproxy_process.pid), signal.SIGTERM)
            except Exception:
                pass
            self.mavproxy_process = None

        if self.arducopter_process:
            try:
                os.killpg(os.getpgid(self.arducopter_process.pid), signal.SIGTERM)
            except Exception:
                pass
            self.arducopter_process = None

        subprocess.run(['pkill', '-f', 'mavproxy'], capture_output=True)
        subprocess.run(['pkill', '-f', 'arducopter'], capture_output=True)

        if had_processes:
            self.log("[CLEANUP] SITL processes stopped")

    def _stop_all_processes(self):
        """Stop all managed processes"""
        # Stop MAVProxy
        if self.mavproxy_process:
            try:
                os.killpg(os.getpgid(self.mavproxy_process.pid), signal.SIGTERM)
            except Exception:
                pass
            self.mavproxy_process = None

        # Stop ArduCopter
        if self.arducopter_process:
            try:
                os.killpg(os.getpgid(self.arducopter_process.pid), signal.SIGTERM)
            except Exception:
                pass
            self.arducopter_process = None

        # Stop GUI
        if self.gui_process:
            try:
                os.killpg(os.getpgid(self.gui_process.pid), signal.SIGTERM)
            except Exception:
                pass
            self.gui_process = None

        # Stop server
        if self.gazebo_process:
            try:
                os.killpg(os.getpgid(self.gazebo_process.pid), signal.SIGTERM)
            except Exception:
                pass
            self.gazebo_process = None

        subprocess.run(['pkill', '-f', 'mavproxy'], capture_output=True)
        subprocess.run(['pkill', '-f', 'arducopter'], capture_output=True)
        subprocess.run(['pkill', '-f', 'gz sim'], capture_output=True)

        self.state.set_gazebo_running(False)
        self.state.set_world(None, None)

    # ====================================================== UI Helpers
    def _set_phase(self, phase: str):
        self.current_phase = phase
        def _update():
            self.phase_var.set(phase)
            if phase == self.PHASE_DONE:
                self.phase_label.config(style='StatusGreen.TLabel')
            elif phase == self.PHASE_ERROR:
                self.phase_label.config(style='StatusRed.TLabel')
            elif phase == self.PHASE_IDLE:
                self.phase_label.config(style='StatusGray.TLabel')
            else:
                self.phase_label.config(style='StatusGreen.TLabel')
        self.after(0, _update)

    def _set_step(self, text: str):
        self.after(0, lambda: self.step_var.set(text))

    def _update_progress(self, current: int, total: int):
        pct = (current / total) * 100 if total > 0 else 0
        self.after(0, lambda: self.progress_var.set(pct))

    def log(self, message: str):
        def _log():
            self.terminal_text.config(state='normal')
            self.terminal_text.insert(tk.END, message + '\n')
            self.terminal_text.see(tk.END)
            self.terminal_text.config(state='disabled')
        self.after(0, _log)

    def clear_log(self):
        self.terminal_text.config(state='normal')
        self.terminal_text.delete(1.0, tk.END)
        self.terminal_text.config(state='disabled')

    # ====================================================== Add / Remove
    def open_add_dialog(self):
        SimulationDialog(self, title="New Simulation",
                         state=self.state,
                         simulations_dir=self.simulations_dir,
                         callback=self.scan_simulations)

    def remove_simulation(self):
        sel = self.sim_listbox.curselection()
        if not sel:
            return
        sim = self.simulations[sel[0]]
        name = sim['name']
        filepath = sim['_path']

        if not messagebox.askyesno("Confirm Delete",
                                   f"Delete '{name}'?\n\nThis will remove:\n{filepath}"):
            return

        try:
            filepath.unlink()
            self.log(f"[INFO] Deleted {filepath.name}")
        except Exception as e:
            self.log(f"[ERROR] Could not delete file: {e}")
            return

        self.scan_simulations()


# ═══════════════════════════════════════════════════════════════════════════
#  Dialog for creating a new .simulation file
# ═══════════════════════════════════════════════════════════════════════════

class SimulationDialog(tk.Toplevel):
    """Dialog for creating a new .simulation file"""

    def __init__(self, parent, title: str, state: GlobalState,
                 simulations_dir: Path, callback=None):
        super().__init__(parent)
        self.callback = callback
        self.state = state
        self.simulations_dir = simulations_dir

        self.title(title)
        self.geometry("580x700")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=COLORS['bg_dark'])

        pad = {'padx': 10, 'pady': 4}
        row = 0

        # ── Simulation name ──
        ttk.Label(self, text="Simulation Name:").grid(row=row, column=0, sticky="w", **pad)
        self.name_var = tk.StringVar()
        ttk.Entry(self, textvariable=self.name_var, width=40).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── File name ──
        ttk.Label(self, text="File Name:").grid(row=row, column=0, sticky="w", **pad)
        fname_frame = ttk.Frame(self)
        fname_frame.grid(row=row, column=1, sticky="ew", **pad)
        self.fname_var = tk.StringVar()
        ttk.Entry(fname_frame, textvariable=self.fname_var, width=30).pack(side=tk.LEFT)
        ttk.Label(fname_frame, text=".simulation").pack(side=tk.LEFT)
        row += 1

        # Auto-generate filename from name
        self.name_var.trace_add('write', self._auto_filename)

        # ── World file ──
        ttk.Label(self, text="World File:").grid(row=row, column=0, sticky="w", **pad)
        self.world_var = tk.StringVar(value='plains_env.sdf')
        ttk.Entry(self, textvariable=self.world_var, width=40).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── World name ──
        ttk.Label(self, text="World Name:").grid(row=row, column=0, sticky="w", **pad)
        self.wname_var = tk.StringVar(value='plains_world')
        ttk.Entry(self, textvariable=self.wname_var, width=40).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── Drone model ──
        ttk.Label(self, text="Drone Model:").grid(row=row, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar(
            value='$ARDUPILOT_GAZEBO/models/iris_with_ardupilot/model.sdf')
        ttk.Entry(self, textvariable=self.model_var, width=40).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── Spawn name ──
        ttk.Label(self, text="Drone Name:").grid(row=row, column=0, sticky="w", **pad)
        self.dname_var = tk.StringVar(value='iris_drone')
        ttk.Entry(self, textvariable=self.dname_var, width=40).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── Spawn position ──
        ttk.Label(self, text="Spawn Position:").grid(row=row, column=0, sticky="w", **pad)
        pos_frame = ttk.Frame(self)
        pos_frame.grid(row=row, column=1, sticky="ew", **pad)

        ttk.Label(pos_frame, text="X:").pack(side=tk.LEFT)
        self.sx_var = tk.StringVar(value='0')
        ttk.Entry(pos_frame, textvariable=self.sx_var, width=6).pack(side=tk.LEFT, padx=(2, 10))

        ttk.Label(pos_frame, text="Y:").pack(side=tk.LEFT)
        self.sy_var = tk.StringVar(value='0')
        ttk.Entry(pos_frame, textvariable=self.sy_var, width=6).pack(side=tk.LEFT, padx=(2, 10))

        ttk.Label(pos_frame, text="Z:").pack(side=tk.LEFT)
        self.sz_var = tk.StringVar(value='0.5')
        ttk.Entry(pos_frame, textvariable=self.sz_var, width=6).pack(side=tk.LEFT, padx=(2, 0))
        row += 1

        # ── Driver (pre-filled with defaults) ──
        ttk.Label(self, text="Driver Binary:").grid(row=row, column=0, sticky="w", **pad)
        self.dbin_var = tk.StringVar(
            value='$ARDUPILOT_HOME/build/sitl/bin/arducopter')
        ttk.Entry(self, textvariable=self.dbin_var, width=40).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(self, text="Driver Defaults:").grid(row=row, column=0, sticky="w", **pad)
        self.ddef_var = tk.StringVar(
            value='default_params/copter.parm,default_params/gazebo-iris.parm')
        ttk.Entry(self, textvariable=self.ddef_var, width=40).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── Flight plan builder ──
        ttk.Label(self, text="Flight Plan:", font=('Segoe UI', 10, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))
        row += 1

        plan_frame = ttk.Frame(self)
        plan_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=10)

        ttk.Label(plan_frame, text="Type:").grid(row=0, column=0)
        self.stype_var = tk.StringVar(value='takeoff')
        ttk.Combobox(plan_frame, textvariable=self.stype_var, state='readonly',
                     values=['takeoff', 'move', 'land'], width=8).grid(row=0, column=1, padx=4)

        ttk.Label(plan_frame, text="Alt:").grid(row=0, column=2)
        self.salt_var = tk.StringVar(value='15')
        ttk.Entry(plan_frame, textvariable=self.salt_var, width=5).grid(row=0, column=3, padx=4)

        ttk.Label(plan_frame, text="X:").grid(row=0, column=4)
        self.smx_var = tk.StringVar(value='0')
        ttk.Entry(plan_frame, textvariable=self.smx_var, width=5).grid(row=0, column=5, padx=4)

        ttk.Label(plan_frame, text="Y:").grid(row=0, column=6)
        self.smy_var = tk.StringVar(value='0')
        ttk.Entry(plan_frame, textvariable=self.smy_var, width=5).grid(row=0, column=7, padx=4)

        ttk.Label(plan_frame, text="Spd:").grid(row=0, column=8)
        self.sspd_var = tk.StringVar(value='1.0')
        ttk.Entry(plan_frame, textvariable=self.sspd_var, width=5).grid(row=0, column=9, padx=4)

        ttk.Button(plan_frame, text="Add", width=5,
                   command=self._add_step).grid(row=0, column=10, padx=4)
        row += 1

        self.flight_steps: List[Dict] = []
        self.steps_listbox = tk.Listbox(self, height=5, font=('Consolas', 9))
        self.steps_listbox.grid(row=row, column=0, columnspan=2, sticky="ew",
                                padx=10, pady=4)
        row += 1

        step_btn_frame = ttk.Frame(self)
        step_btn_frame.grid(row=row, column=0, columnspan=2, padx=10)
        ttk.Button(step_btn_frame, text="Remove",
                   command=self._remove_step).pack(side=tk.LEFT, padx=5)
        ttk.Button(step_btn_frame, text="Clear",
                   command=self._clear_steps).pack(side=tk.LEFT, padx=5)
        row += 1

        # ── Description ──
        ttk.Label(self, text="Description:").grid(row=row, column=0, sticky="nw", **pad)
        self.desc_text = tk.Text(self, width=40, height=3, font=('Segoe UI', 9),
                                 bg=COLORS['bg_light'], fg=COLORS['fg_primary'],
                                 insertbackground=COLORS['fg_primary'],
                                 relief='flat')
        self.desc_text.grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        # ── Buttons ──
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=12)
        ttk.Button(btn_frame, text="Save", command=self._on_save,
                   style='Accent.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side=tk.LEFT, padx=10)

        self.columnconfigure(1, weight=1)

    def _add_step(self):
        stype = self.stype_var.get()
        step = {'type': stype}
        try:
            if stype == 'takeoff':
                step['altitude'] = float(self.salt_var.get())
                label = f"Takeoff {step['altitude']}m"
            elif stype == 'move':
                step['x'] = float(self.smx_var.get())
                step['y'] = float(self.smy_var.get())
                step['speed'] = float(self.sspd_var.get())
                label = f"Move X={step['x']} Y={step['y']} @ {step['speed']}m/s"
            else:
                label = "Land"
        except ValueError:
            messagebox.showwarning("Invalid", "Enter valid numbers", parent=self)
            return
        self.flight_steps.append(step)
        self.steps_listbox.insert(tk.END, f"{len(self.flight_steps)}: {label}")

    def _remove_step(self):
        sel = self.steps_listbox.curselection()
        if sel:
            self.flight_steps.pop(sel[0])
            self._refresh_steps()

    def _clear_steps(self):
        self.flight_steps.clear()
        self.steps_listbox.delete(0, tk.END)

    def _refresh_steps(self):
        self.steps_listbox.delete(0, tk.END)
        for i, s in enumerate(self.flight_steps, 1):
            if s['type'] == 'takeoff':
                label = f"Takeoff {s['altitude']}m"
            elif s['type'] == 'move':
                label = f"Move X={s['x']} Y={s['y']} @ {s.get('speed', 1)}m/s"
            else:
                label = "Land"
            self.steps_listbox.insert(tk.END, f"{i}: {label}")

    def _auto_filename(self, *_):
        """Auto-generate a filename from the simulation name"""
        name = self.name_var.get().strip()
        fname = name.lower().replace(' ', '_').replace('—', '_').replace('-', '_')
        fname = ''.join(c for c in fname if c.isalnum() or c == '_')
        while '__' in fname:
            fname = fname.replace('__', '_')
        fname = fname.strip('_')
        self.fname_var.set(fname)

    def _on_save(self):
        name = self.name_var.get().strip()
        fname = self.fname_var.get().strip()

        if not name:
            messagebox.showwarning("Missing", "Name is required", parent=self)
            return
        if not fname:
            messagebox.showwarning("Missing", "File name is required", parent=self)
            return
        if not self.flight_steps:
            messagebox.showwarning("Missing", "Add at least one flight step", parent=self)
            return

        try:
            x = float(self.sx_var.get())
            y = float(self.sy_var.get())
            z = float(self.sz_var.get())
        except ValueError:
            messagebox.showwarning("Invalid", "Spawn position must be numbers", parent=self)
            return

        sim_data = {
            "name": name,
            "description": self.desc_text.get('1.0', tk.END).strip(),
            "environment": {
                "world_file": self.world_var.get().strip(),
                "world_name": self.wname_var.get().strip() or None,
            },
            "drone": {
                "model_path": self.model_var.get().strip(),
                "spawn_name": self.dname_var.get().strip(),
                "spawn_position": [x, y, z],
            },
            "driver": {
                "binary": self.dbin_var.get().strip(),
                "defaults": self.ddef_var.get().strip(),
                "working_dir": "$ARDUPILOT_HOME/Tools/autotest",
            },
            "flight_plan": list(self.flight_steps),
        }

        # Remove None values
        if sim_data['environment']['world_name'] is None:
            del sim_data['environment']['world_name']

        filepath = self.simulations_dir / f"{fname}.simulation"
        if filepath.exists():
            if not messagebox.askyesno("Overwrite?",
                                       f"{filepath.name} already exists. Overwrite?",
                                       parent=self):
                return

        try:
            with open(filepath, 'w') as f:
                json.dump(sim_data, f, indent=4)
        except Exception as e:
            messagebox.showerror("Error", f"Could not save file: {e}", parent=self)
            return

        if self.callback:
            self.callback()
        self.destroy()
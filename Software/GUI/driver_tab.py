"""
driver_tab.py - Tab for managing and launching flight controller drivers
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import subprocess
import os
import signal
import threading
import json
from pathlib import Path
from typing import Dict, List, Optional

from .global_state import GlobalState
from .theme import get_terminal_colors, COLORS


# Default built-in driver configurations
BUILTIN_DRIVERS = [
    {
        'name': 'ArduCopter SITL',
        'description': 'ArduPilot Software-In-The-Loop for multicopters.\n'
                       'Connects to Gazebo via JSON interface.',
        'command': 'sim_vehicle.py',
        'args': '-v ArduCopter -f gazebo-iris --model JSON --console',
        'working_dir': '$ARDUPILOT_HOME/Tools/autotest',
        'builtin': True,
        'env_vars': {},
    },
    {
        'name': 'ArduPlane SITL',
        'description': 'ArduPilot SITL for fixed-wing aircraft.',
        'command': 'sim_vehicle.py',
        'args': '-v ArduPlane -f gazebo-iris --model JSON --console',
        'working_dir': '$ARDUPILOT_HOME/Tools/autotest',
        'builtin': True,
        'env_vars': {},
    },
    {
        'name': 'ArduRover SITL',
        'description': 'ArduPilot SITL for ground rovers.',
        'command': 'sim_vehicle.py',
        'args': '-v Rover -f gazebo-iris --model JSON --console',
        'working_dir': '$ARDUPILOT_HOME/Tools/autotest',
        'builtin': True,
        'env_vars': {},
    },
]


class DriverTab(ttk.Frame):
    """Tab for managing and launching flight controller drivers"""

    def __init__(self, parent, state: GlobalState):
        super().__init__(parent, padding="10")
        self.state = state
        self.driver_process: Optional[subprocess.Popen] = None
        self.is_driver_running = False
        self.output_thread: Optional[threading.Thread] = None

        self.ardupilot_home = state.ros2_tools_path / "ArduPilot" / "ardupilot"
        self.config_path = state.ros2_tools_path / "Software" / "GUI" / "custom_drivers.json"

        self.drivers: List[Dict] = []

        state.add_listener(self.on_state_changed)

        self.setup_gui()
        self.load_drivers()

    def setup_gui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # Status bar
        status_frame = ttk.Frame(self)
        status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ttk.Label(status_frame, text="Driver Status:").pack(side=tk.LEFT)
        self.driver_status_var = tk.StringVar(value="Stopped")
        self.driver_status_label = ttk.Label(
            status_frame, textvariable=self.driver_status_var,
            style='StatusRed.TLabel')
        self.driver_status_label.pack(side=tk.LEFT, padx=(5, 20))

        ttk.Label(status_frame, text="Environment:").pack(side=tk.LEFT)
        self.env_status_var = tk.StringVar(value="None")
        self.env_status_label = ttk.Label(
            status_frame, textvariable=self.env_status_var,
            style='StatusGray.TLabel')
        self.env_status_label.pack(side=tk.LEFT, padx=(5, 0))

        # Left panel – Driver list
        left_frame = ttk.LabelFrame(self, text="Available Drivers", padding="10")
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.driver_listbox = tk.Listbox(
            list_frame, font=('Consolas', 10),
            selectmode=tk.SINGLE, exportselection=False)
        self.driver_listbox.grid(row=0, column=0, sticky="nsew")
        self.driver_listbox.bind('<<ListboxSelect>>', self.on_driver_selected)

        scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL,
            command=self.driver_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.driver_listbox.config(yscrollcommand=scrollbar.set)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        ttk.Button(btn_frame, text="+ Add Custom",
                   command=self.open_add_dialog).grid(row=0, column=0, sticky="ew", padx=(0, 2))
        ttk.Button(btn_frame, text="Edit",
                   command=self.open_edit_dialog).grid(row=0, column=1, sticky="ew", padx=2)
        self.remove_btn = ttk.Button(btn_frame, text="Remove",
                                     command=self.remove_driver, state='disabled')
        self.remove_btn.grid(row=0, column=2, sticky="ew", padx=(2, 0))

        # Right panel – Details / Controls / Output
        right_frame = ttk.Frame(self)
        right_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(2, weight=1)

        # Driver details
        details_frame = ttk.LabelFrame(right_frame, text="Driver Details", padding="10")
        details_frame.grid(row=0, column=0, sticky="ew")
        details_frame.columnconfigure(1, weight=1)

        ttk.Label(details_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=2)
        self.detail_name_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_name_var,
                  font=('Segoe UI', 10, 'bold')).grid(row=0, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="Command:").grid(row=1, column=0, sticky="w", pady=2)
        self.detail_cmd_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_cmd_var,
                  font=('Consolas', 9), wraplength=380).grid(row=1, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="Work Dir:").grid(row=2, column=0, sticky="w", pady=2)
        self.detail_dir_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_dir_var,
                  font=('Consolas', 9), wraplength=380).grid(row=2, column=1, sticky="w", padx=(10, 0))

        ttk.Label(details_frame, text="Info:").grid(row=3, column=0, sticky="nw", pady=2)
        self.detail_desc_var = tk.StringVar(value="—")
        ttk.Label(details_frame, textvariable=self.detail_desc_var,
                  wraplength=380).grid(row=3, column=1, sticky="w", padx=(10, 0))

        # Launch controls
        ctrl_frame = ttk.LabelFrame(right_frame, text="Controls", padding="10")
        ctrl_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=1)

        self.launch_btn = ttk.Button(
            ctrl_frame, text="▶  Launch Driver",
            command=self.launch_driver, state='disabled',
            style='Accent.TButton')
        self.launch_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=5)

        self.stop_btn = ttk.Button(
            ctrl_frame, text="⏹  Stop Driver",
            command=self.stop_driver, state='disabled',
            style='Danger.TButton')
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=5)

        # Terminal output
        term_frame = ttk.LabelFrame(right_frame, text="Driver Output", padding="10")
        term_frame.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        term_frame.columnconfigure(0, weight=1)
        term_frame.rowconfigure(0, weight=1)

        tc = get_terminal_colors()
        self.terminal_text = scrolledtext.ScrolledText(
            term_frame, height=12, font=('Consolas', 9),
            state='disabled',
            bg=tc['bg'], fg=tc['fg'],
            selectbackground=tc['select_bg'],
            selectforeground=tc['select_fg'],
            insertbackground=tc['fg'],
            relief='flat', borderwidth=0)
        self.terminal_text.grid(row=0, column=0, sticky="nsew")

        ttk.Button(term_frame, text="Clear Log",
                   command=self.clear_log).grid(row=1, column=0, sticky="e", pady=(5, 0))

    # --------------------------------------------------------- Driver list
    def load_drivers(self):
        self.drivers.clear()
        self.driver_listbox.delete(0, tk.END)

        for drv in BUILTIN_DRIVERS:
            self.drivers.append(dict(drv))

        custom = self._load_custom_config()
        for drv in custom:
            drv['builtin'] = False
            self.drivers.append(drv)

        for drv in self.drivers:
            tag = "Built-in" if drv.get('builtin') else "Custom"
            self.driver_listbox.insert(tk.END, f"{drv['name']}  [{tag}]")

    def _load_custom_config(self) -> List[Dict]:
        if not self.config_path.exists():
            return []
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_custom_config(self):
        custom = [d for d in self.drivers if not d.get('builtin')]
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(custom, f, indent=2)

    # --------------------------------------------------------- Selection
    def on_driver_selected(self, event=None):
        sel = self.driver_listbox.curselection()
        if not sel:
            return
        drv = self.drivers[sel[0]]

        self.detail_name_var.set(drv['name'])
        full_cmd = f"{drv['command']} {drv.get('args', '')}".strip()
        self.detail_cmd_var.set(full_cmd)
        self.detail_dir_var.set(drv.get('working_dir', '(default)'))
        self.detail_desc_var.set(drv.get('description', ''))

        is_custom = not drv.get('builtin')
        self.remove_btn.config(state='normal' if is_custom else 'disabled')
        self.launch_btn.config(state='normal' if not self.is_driver_running else 'disabled')

    # --------------------------------------------------------- State events
    def on_state_changed(self, event: str):
        if event in ('world_changed', 'gazebo_state_changed'):
            self.after(0, self._update_env_status)
        if event == 'driver_state_changed':
            self.after(0, self._update_driver_ui)

    def _update_env_status(self):
        if self.state.current_world and self.state.is_gazebo_running:
            self.env_status_var.set(self.state.current_world)
            self.env_status_label.config(style='StatusGreen.TLabel')
        else:
            self.env_status_var.set("None")
            self.env_status_label.config(style='StatusGray.TLabel')

    def _update_driver_ui(self):
        if self.is_driver_running:
            self.driver_status_var.set("Running")
            self.driver_status_label.config(style='StatusGreen.TLabel')
            self.launch_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
        else:
            self.driver_status_var.set("Stopped")
            self.driver_status_label.config(style='StatusRed.TLabel')
            self.stop_btn.config(state='disabled')
            sel = self.driver_listbox.curselection()
            self.launch_btn.config(state='normal' if sel else 'disabled')

    # ------------------------------------------------------ Launch / Stop
    def _resolve_path(self, raw: str) -> str:
        resolved = raw.replace('$ARDUPILOT_HOME', str(self.ardupilot_home))
        resolved = os.path.expanduser(resolved)
        resolved = os.path.expandvars(resolved)
        return resolved

    def launch_driver(self):
        sel = self.driver_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Driver", "Select a driver first")
            return
        if self.is_driver_running:
            messagebox.showwarning("Already Running", "Stop the current driver first")
            return

        drv = self.drivers[sel[0]]
        full_cmd = f"{drv['command']} {drv.get('args', '')}".strip()
        work_dir = self._resolve_path(drv.get('working_dir', ''))
        if not work_dir or not Path(work_dir).is_dir():
            work_dir = str(Path.home())

        self.log(f"\n{'=' * 40}")
        self.log(f"[LAUNCH] {drv['name']}")
        self.log(f"[CMD]    {full_cmd}")
        self.log(f"[DIR]    {work_dir}")
        self.log(f"{'=' * 40}\n")

        thread = threading.Thread(
            target=self._run_driver,
            args=(full_cmd, work_dir, drv.get('env_vars', {})),
            daemon=True)
        thread.start()

    def _run_driver(self, cmd: str, work_dir: str, extra_env: Dict):
        try:
            env = os.environ.copy()
            env.update(extra_env)

            # Clean snap paths from LD_LIBRARY_PATH to prevent gnome-terminal crash
            # (Ubuntu 24.04 + VirtualBox snap libpthread conflict)
            snap_clean = (
                'export LD_LIBRARY_PATH='
                '$(echo "$LD_LIBRARY_PATH" | tr \':\' \'\\n\' | '
                'grep -v \'/snap/\' | tr \'\\n\' \':\' | sed \'s/:$//\') && '
            )

            setup_script = self.state.ros2_tools_path / "ArduPilot" / "setup_ardupilot_env.sh"
            if setup_script.exists():
                wrapped = f'{snap_clean}source /opt/ros/jazzy/setup.bash && source {setup_script} && cd {work_dir} && {cmd}'
            else:
                wrapped = f'{snap_clean}source /opt/ros/jazzy/setup.bash && cd {work_dir} && {cmd}'

            self.driver_process = subprocess.Popen(
                ['bash', '-c', wrapped],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                preexec_fn=os.setsid,
            )

            self.is_driver_running = True
            self.state.notify_listeners('driver_state_changed')

            for line in iter(self.driver_process.stdout.readline, ''):
                if line:
                    self.after(0, lambda l=line: self.log(l.rstrip()))

            self.driver_process.wait()

        except Exception as e:
            self.after(0, lambda: self.log(f"[ERROR] {e}"))
        finally:
            self.is_driver_running = False
            self.driver_process = None
            self.state.notify_listeners('driver_state_changed')
            self.after(0, lambda: self.log("\n[INFO] Driver stopped"))

    def stop_driver(self):
        if self.driver_process:
            self.log("[STOP] Terminating driver...")
            try:
                os.killpg(os.getpgid(self.driver_process.pid), signal.SIGTERM)
            except Exception:
                pass
        subprocess.run(['pkill', '-f', 'sim_vehicle.py'], capture_output=True)

    # ------------------------------------------- Add / Edit / Remove custom
    def open_add_dialog(self):
        DriverDialog(self, title="Add Custom Driver", callback=self._on_driver_added)

    def open_edit_dialog(self):
        sel = self.driver_listbox.curselection()
        if not sel:
            messagebox.showwarning("No Selection", "Select a driver to edit")
            return
        drv = self.drivers[sel[0]]
        if drv.get('builtin'):
            messagebox.showinfo("Built-in", "Built-in drivers cannot be edited.\n"
                                "Add a custom copy instead.")
            return
        DriverDialog(self, title="Edit Driver", driver=drv,
                     callback=lambda d: self._on_driver_edited(sel[0], d))

    def _on_driver_added(self, drv: Dict):
        drv['builtin'] = False
        self.drivers.append(drv)
        self.driver_listbox.insert(tk.END, f"{drv['name']}  [Custom]")
        self._save_custom_config()

    def _on_driver_edited(self, index: int, drv: Dict):
        drv['builtin'] = False
        self.drivers[index] = drv
        self.driver_listbox.delete(index)
        self.driver_listbox.insert(index, f"{drv['name']}  [Custom]")
        self._save_custom_config()
        self.driver_listbox.selection_set(index)
        self.on_driver_selected()

    def remove_driver(self):
        sel = self.driver_listbox.curselection()
        if not sel:
            return
        drv = self.drivers[sel[0]]
        if drv.get('builtin'):
            messagebox.showinfo("Built-in", "Cannot remove built-in drivers")
            return
        if not messagebox.askyesno("Confirm", f"Remove '{drv['name']}'?"):
            return
        self.drivers.pop(sel[0])
        self.driver_listbox.delete(sel[0])
        self._save_custom_config()
        self.detail_name_var.set("—")
        self.detail_cmd_var.set("—")
        self.detail_dir_var.set("—")
        self.detail_desc_var.set("—")

    # ------------------------------------------------------------ Logging
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


# ═══════════════════════════════════════════════════════════════════════════
#  Dialog for adding / editing custom drivers
# ═══════════════════════════════════════════════════════════════════════════

class DriverDialog(tk.Toplevel):
    """Modal dialog for creating or editing a custom driver configuration"""

    def __init__(self, parent, title: str, driver: Optional[Dict] = None,
                 callback=None):
        super().__init__(parent)
        self.callback = callback
        self.result: Optional[Dict] = None

        self.title(title)
        self.geometry("520x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Apply dark background to dialog
        self.configure(bg=COLORS['bg_dark'])

        pad = {'padx': 10, 'pady': 4}
        row = 0

        ttk.Label(self, text="Driver Name:").grid(row=row, column=0, sticky="w", **pad)
        self.name_var = tk.StringVar(value=driver.get('name', '') if driver else '')
        ttk.Entry(self, textvariable=self.name_var, width=50).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(self, text="Command:").grid(row=row, column=0, sticky="w", **pad)
        self.cmd_var = tk.StringVar(value=driver.get('command', '') if driver else '')
        ttk.Entry(self, textvariable=self.cmd_var, width=50).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(self, text="Arguments:").grid(row=row, column=0, sticky="w", **pad)
        self.args_var = tk.StringVar(value=driver.get('args', '') if driver else '')
        ttk.Entry(self, textvariable=self.args_var, width=50).grid(
            row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(self, text="Working Dir:").grid(row=row, column=0, sticky="w", **pad)
        dir_frame = ttk.Frame(self)
        dir_frame.grid(row=row, column=1, sticky="ew", **pad)
        dir_frame.columnconfigure(0, weight=1)
        self.dir_var = tk.StringVar(
            value=driver.get('working_dir', '') if driver else '')
        ttk.Entry(dir_frame, textvariable=self.dir_var).grid(
            row=0, column=0, sticky="ew")
        ttk.Button(dir_frame, text="Browse",
                   command=self._browse_dir).grid(row=0, column=1, padx=(5, 0))
        row += 1

        ttk.Label(self, text="Description:").grid(row=row, column=0, sticky="nw", **pad)
        self.desc_text = tk.Text(self, width=50, height=5, font=('Segoe UI', 9),
                                 bg=COLORS['bg_light'], fg=COLORS['fg_primary'],
                                 insertbackground=COLORS['fg_primary'],
                                 selectbackground=COLORS['bg_selected'],
                                 relief='flat')
        self.desc_text.grid(row=row, column=1, sticky="ew", **pad)
        if driver and driver.get('description'):
            self.desc_text.insert('1.0', driver['description'])
        row += 1

        ttk.Label(self, text="Tip: Use $ARDUPILOT_HOME for the ArduPilot directory",
                  foreground=COLORS['fg_muted']).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(5, 0))
        row += 1

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Save", command=self._on_save,
                   style='Accent.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side=tk.LEFT, padx=10)

        self.columnconfigure(1, weight=1)

    def _browse_dir(self):
        d = filedialog.askdirectory(title="Select Working Directory")
        if d:
            self.dir_var.set(d)

    def _on_save(self):
        name = self.name_var.get().strip()
        cmd = self.cmd_var.get().strip()
        if not name:
            messagebox.showwarning("Missing", "Driver name is required", parent=self)
            return
        if not cmd:
            messagebox.showwarning("Missing", "Command is required", parent=self)
            return

        self.result = {
            'name': name,
            'command': cmd,
            'args': self.args_var.get().strip(),
            'working_dir': self.dir_var.get().strip(),
            'description': self.desc_text.get('1.0', tk.END).strip(),
            'env_vars': {},
        }
        if self.callback:
            self.callback(self.result)
        self.destroy()
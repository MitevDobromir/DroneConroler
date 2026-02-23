"""
controller_tab.py - Tab for controlling drones
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sys
import threading
from pathlib import Path
from typing import List, Dict, Tuple

from .global_state import GlobalState
from .theme import get_terminal_colors, COLORS

# Try to import flight controller
try:
    sys.path.insert(0, str(Path.home() / "ROS2_Tools" / "Software" / "Common"))
    from flight_controller import DroneController
    FLIGHT_CONTROLLER_AVAILABLE = True
except ImportError:
    FLIGHT_CONTROLLER_AVAILABLE = False


class ControllerTab(ttk.Frame):
    """Tab for controlling drones via MAVLink"""
    
    STEP_TYPES: Dict[str, List[Tuple]] = {
        'Takeoff': [('altitude', 'Altitude (m)', '5', 1, 50)],
        'Move': [
            ('x', 'X (m)', '0', -100, 100),
            ('y', 'Y (m)', '0', -100, 100),
            ('speed', 'Speed (m/s)', '1.0', 0.1, 10)
        ],
        'Land': []
    }
    
    def __init__(self, parent, state: GlobalState):
        super().__init__(parent, padding="10")
        self.state = state
        self.drone_controller = None
        self.is_connected = False
        self.gps_update_active = False
        self.is_mission_running = False
        
        self.mission_steps: List[Dict] = []
        
        state.add_listener(self.on_state_changed)
        
        self.setup_gui()
        
    def setup_gui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Connection and GPS frame
        top_frame = ttk.Frame(self)
        top_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        top_frame.columnconfigure(1, weight=1)
        
        # Connection frame
        conn_frame = ttk.LabelFrame(top_frame, text="Connection", padding="5")
        conn_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.connect_button = ttk.Button(conn_frame, text="Connect",
                                         command=self.toggle_connection,
                                         style='Accent.TButton')
        self.connect_button.pack(side=tk.LEFT, padx=5)
        
        self.conn_status_var = tk.StringVar(value="Disconnected")
        self.conn_status_label = ttk.Label(conn_frame, textvariable=self.conn_status_var,
                                           style='StatusRed.TLabel')
        self.conn_status_label.pack(side=tk.LEFT, padx=10)
        
        # GPS frame
        gps_frame = ttk.LabelFrame(top_frame, text="GPS", padding="5")
        gps_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        self.lat_var = tk.StringVar(value="---")
        self.lon_var = tk.StringVar(value="---")
        self.alt_var = tk.StringVar(value="---")
        
        ttk.Label(gps_frame, text="Lat:").pack(side=tk.LEFT)
        ttk.Label(gps_frame, textvariable=self.lat_var, width=12,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        ttk.Label(gps_frame, text="Lon:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(gps_frame, textvariable=self.lon_var, width=12,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        ttk.Label(gps_frame, text="Alt:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Label(gps_frame, textvariable=self.alt_var, width=8,
                 font=('Consolas', 9)).pack(side=tk.LEFT)
        
        # Left panel - Mission builder
        left_frame = ttk.LabelFrame(self, text="Mission Builder", padding="10")
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(4, weight=1)
        
        ttk.Label(left_frame, text="Step Type:").grid(row=0, column=0, sticky="w")
        self.step_type_var = tk.StringVar(value="Takeoff")
        self.step_combo = ttk.Combobox(left_frame, textvariable=self.step_type_var,
                                       state='readonly',
                                       values=list(self.STEP_TYPES.keys()))
        self.step_combo.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.step_combo.bind('<<ComboboxSelected>>', self.on_step_type_changed)
        
        self.params_frame = ttk.Frame(left_frame)
        self.params_frame.grid(row=2, column=0, sticky="ew")
        self.param_widgets: Dict = {}
        
        self.on_step_type_changed()
        
        ttk.Button(left_frame, text="Add Step",
                  command=self.add_step).grid(row=3, column=0, pady=10, sticky="ew")
        
        ttk.Separator(left_frame, orient=tk.HORIZONTAL).grid(row=4, column=0, sticky="ew", pady=10)
        
        ttk.Label(left_frame, text="Mission Steps:").grid(row=5, column=0, sticky="w")
        
        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=6, column=0, sticky="nsew", pady=(5, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.mission_listbox = tk.Listbox(list_frame, height=8, font=('Consolas', 9))
        self.mission_listbox.grid(row=0, column=0, sticky="nsew")
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                 command=self.mission_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.mission_listbox.config(yscrollcommand=scrollbar.set)
        
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=7, column=0, sticky="ew", pady=(5, 0))
        ttk.Button(btn_frame, text="Remove",
                  command=self.remove_step).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btn_frame, text="Clear",
                  command=self.clear_steps).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(5, 0))
        
        # Right panel - Execution
        right_frame = ttk.LabelFrame(self, text="Execution", padding="10")
        right_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        self.run_button = ttk.Button(right_frame, text="▶  Run Mission",
                                     command=self.run_mission, state='disabled',
                                     style='Success.TButton')
        self.run_button.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        tc = get_terminal_colors()
        self.status_text = scrolledtext.ScrolledText(
            right_frame, height=15,
            font=('Consolas', 9), state='disabled',
            bg=tc['bg'], fg=tc['fg'],
            selectbackground=tc['select_bg'],
            selectforeground=tc['select_fg'],
            insertbackground=tc['fg'],
            relief='flat', borderwidth=0)
        self.status_text.grid(row=1, column=0, sticky="nsew")
        
        ttk.Button(right_frame, text="Clear Log",
                  command=self.clear_log).grid(row=2, column=0, sticky="e", pady=(5, 0))
        
    def on_state_changed(self, event: str):
        if event == 'drone_spawned':
            self.after(0, self.update_drone_list)
            
    def update_drone_list(self):
        pass
        
    def on_step_type_changed(self, event=None):
        for widget in self.params_frame.winfo_children():
            widget.destroy()
        self.param_widgets.clear()
        
        step_type = self.step_type_var.get()
        params = self.STEP_TYPES[step_type]
        
        for i, (name, label, default, min_val, max_val) in enumerate(params):
            ttk.Label(self.params_frame, text=f"{label}:").grid(row=i, column=0, sticky="w", pady=2)
            entry = ttk.Entry(self.params_frame, width=15)
            entry.insert(0, default)
            entry.grid(row=i, column=1, sticky="w", pady=2, padx=(10, 0))
            self.param_widgets[name] = {
                'widget': entry,
                'min': min_val,
                'max': max_val
            }
            
    def add_step(self):
        step_type = self.step_type_var.get()
        step = {'type': step_type.lower()}
        
        params = self.STEP_TYPES[step_type]
        try:
            for name, label, _, min_val, max_val in params:
                value = float(self.param_widgets[name]['widget'].get())
                if value < min_val or value > max_val:
                    messagebox.showerror("Error", f"{label} must be between {min_val} and {max_val}")
                    return
                step[name] = value
        except ValueError:
            messagebox.showerror("Error", "Invalid parameter value")
            return
            
        self.mission_steps.append(step)
        
        display = f"{len(self.mission_steps)}: {step_type}"
        if params:
            param_str = ", ".join([f"{p[0]}={step[p[0]]}" for p in params])
            display += f" ({param_str})"
        self.mission_listbox.insert(tk.END, display)
        
    def remove_step(self):
        selection = self.mission_listbox.curselection()
        if selection:
            self.mission_steps.pop(selection[0])
            self.refresh_mission_list()
            
    def clear_steps(self):
        self.mission_steps.clear()
        self.mission_listbox.delete(0, tk.END)
        
    def refresh_mission_list(self):
        self.mission_listbox.delete(0, tk.END)
        for i, step in enumerate(self.mission_steps, 1):
            step_type = step['type'].capitalize()
            params = self.STEP_TYPES.get(step_type, [])
            display = f"{i}: {step_type}"
            if params:
                param_str = ", ".join([f"{p[0]}={step.get(p[0], '')}" for p in params])
                display += f" ({param_str})"
            self.mission_listbox.insert(tk.END, display)
            
    def toggle_connection(self):
        if self.is_connected:
            self.disconnect()
        else:
            self.connect()
            
    def connect(self):
        if not FLIGHT_CONTROLLER_AVAILABLE:
            messagebox.showerror("Error",
                "Flight controller module not available.\n"
                "Make sure flight_controller.py exists in:\n"
                "~/ROS2_Tools/Software/Common/")
            return
            
        try:
            self.log("[CONNECT] Connecting to drone...")
            self.drone_controller = DroneController()
            self.is_connected = True
            self.connect_button.config(text="Disconnect")
            self.conn_status_var.set("Connected")
            self.conn_status_label.config(style='StatusGreen.TLabel')
            self.run_button.config(state='normal')
            self.log("[SUCCESS] Connected!")
            
            self.gps_update_active = True
            self.update_gps()
            
        except Exception as e:
            self.log(f"[ERROR] Connection failed: {e}")
            messagebox.showerror("Connection Error", str(e))
            
    def disconnect(self):
        self.gps_update_active = False
        self.drone_controller = None
        self.is_connected = False
        self.connect_button.config(text="Connect")
        self.conn_status_var.set("Disconnected")
        self.conn_status_label.config(style='StatusRed.TLabel')
        self.run_button.config(state='disabled')
        self.lat_var.set("---")
        self.lon_var.set("---")
        self.alt_var.set("---")
        self.log("[INFO] Disconnected")
        
    def update_gps(self):
        if not self.gps_update_active or not self.drone_controller:
            return
            
        def fetch():
            try:
                loc = self.drone_controller.get_location()
                if loc:
                    self.after(0, lambda: self._update_gps_display(loc))
            except Exception:
                pass
                
            if self.gps_update_active:
                self.after(500, self.update_gps)
                
        thread = threading.Thread(target=fetch, daemon=True)
        thread.start()
        
    def _update_gps_display(self, loc: Dict):
        self.lat_var.set(f"{loc['lat']:.6f}")
        self.lon_var.set(f"{loc['lon']:.6f}")
        self.alt_var.set(f"{loc['relative_alt']:.1f}m")
        
    def run_mission(self):
        if not self.mission_steps:
            messagebox.showwarning("No Mission", "Add steps to mission first")
            return
        if not self.is_connected:
            messagebox.showerror("Not Connected", "Connect to drone first")
            return
        if self.is_mission_running:
            messagebox.showwarning("Running", "Mission already running")
            return
            
        thread = threading.Thread(target=self._execute_mission)
        thread.daemon = True
        thread.start()
        
    def _execute_mission(self):
        self.is_mission_running = True
        self.after(0, lambda: self.run_button.config(state='disabled'))
        
        try:
            self.log("\n" + "=" * 40)
            self.log("[MISSION] Starting...")
            self.log("=" * 40)
            
            self.log("\n[SETUP] Waiting for GPS lock...")
            if not self.drone_controller.wait_for_gps():
                self.log("[ERROR] GPS timeout - aborting mission")
                return
                
            self.log("[SETUP] Setting GUIDED mode...")
            if not self.drone_controller.set_mode('GUIDED'):
                self.log("[ERROR] Failed to set mode - aborting mission")
                return
                
            self.log("[SETUP] Arming motors...")
            if not self.drone_controller.arm():
                self.log("[ERROR] Arming failed - aborting mission")
                return
                
            self.log("[SETUP] Ready for mission!\n")
            
            for i, step in enumerate(self.mission_steps, 1):
                step_type = step['type']
                self.log(f"[STEP {i}/{len(self.mission_steps)}] {step_type.upper()}")
                
                if step_type == 'takeoff':
                    altitude = step['altitude']
                    self.log(f"  Taking off to {altitude}m...")
                    if not self.drone_controller.takeoff(altitude):
                        self.log("[ERROR] Takeoff failed")
                        break
                        
                elif step_type == 'move':
                    x, y = step['x'], step['y']
                    speed = step.get('speed', 1.0)
                    self.log(f"  Moving X={x}m, Y={y}m at {speed}m/s...")
                    if not self.drone_controller.move_relative(x, y, speed):
                        self.log("[ERROR] Move failed")
                        break
                        
                elif step_type == 'land':
                    self.log("  Landing...")
                    self.drone_controller.land()
                    
                self.log(f"  Done\n")
                
            self.log("=" * 40)
            self.log("[MISSION] Complete!")
            self.log("=" * 40)
            
        except Exception as e:
            self.log(f"\n[ERROR] Mission failed: {e}")
            if self.drone_controller:
                self.log("[SAFETY] Emergency landing...")
                self.drone_controller.land()
        finally:
            self.is_mission_running = False
            self.after(0, lambda: self.run_button.config(
                state='normal' if self.is_connected else 'disabled'))
            
    def log(self, message: str):
        def _log():
            self.status_text.config(state='normal')
            self.status_text.insert(tk.END, message + '\n')
            self.status_text.see(tk.END)
            self.status_text.config(state='disabled')
        self.after(0, _log)
        
    def clear_log(self):
        self.status_text.config(state='normal')
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state='disabled')
"""
spawner_tab.py - Tab for spawning drones
"""
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
from pathlib import Path
from typing import Dict

# Try to import PIL for image preview
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from .global_state import GlobalState
from .theme import COLORS


class SpawnerTab(ttk.Frame):
    """Tab for spawning drones into the simulation"""
    
    def __init__(self, parent, state: GlobalState):
        super().__init__(parent, padding="10")
        self.state = state
        
        # Model directories to scan
        self.model_directories = [
            {
                'path': state.ros2_tools_path / "Models",
                'type': 'flat',
                'name': 'Custom'
            },
            {
                'path': state.ros2_tools_path / "ArduPilot" / "ardupilot_gazebo" / "models",
                'type': 'folder',
                'name': 'ArduPilot'
            }
        ]
        
        # Preview directories
        self.preview_directories = [
            state.ros2_tools_path / "Models" / "previews",
            state.ros2_tools_path / "ArduPilot" / "ardupilot_gazebo" / "models" / "previews"
        ]
        
        self.models = []
        self.current_preview = None
        self.spawn_counter = 1
        
        state.add_listener(self.on_state_changed)
        
        self.setup_gui()
        self.scan_models()
        
    def setup_gui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        
        # World status bar
        status_frame = ttk.Frame(self)
        status_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        ttk.Label(status_frame, text="Current World:").pack(side=tk.LEFT)
        self.world_status_var = tk.StringVar(value="No environment running")
        self.world_status_label = ttk.Label(status_frame, textvariable=self.world_status_var,
                                            style='StatusRed.TLabel')
        self.world_status_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Left panel - Model selection
        left_frame = ttk.LabelFrame(self, text="Available Models", padding="10")
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)
        
        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.model_listbox = tk.Listbox(list_frame, font=('Consolas', 10),
                                        selectmode=tk.SINGLE, exportselection=False)
        self.model_listbox.grid(row=0, column=0, sticky="nsew")
        self.model_listbox.bind('<<ListboxSelect>>', self.on_model_selected)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                 command=self.model_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.model_listbox.config(yscrollcommand=scrollbar.set)
        
        ttk.Button(left_frame, text="Refresh",
                  command=self.scan_models).grid(row=1, column=0, pady=(10, 0), sticky="ew")
        
        # Right panel
        right_frame = ttk.Frame(self)
        right_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        # Preview
        preview_frame = ttk.LabelFrame(right_frame, text="Model Preview", padding="10")
        preview_frame.grid(row=0, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        
        self.preview_label = ttk.Label(preview_frame, text="Select a model",
                                       anchor=tk.CENTER,
                                       foreground=COLORS['fg_muted'])
        self.preview_label.grid(row=0, column=0, sticky="nsew")
        
        self.model_info_var = tk.StringVar(value="")
        ttk.Label(preview_frame, textvariable=self.model_info_var,
                 wraplength=300).grid(row=1, column=0, pady=(10, 0))
        
        # Spawn parameters
        params_frame = ttk.LabelFrame(right_frame, text="Spawn Parameters", padding="10")
        params_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        params_frame.columnconfigure(1, weight=1)
        
        ttk.Label(params_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=5)
        self.name_var = tk.StringVar(value="drone_1")
        ttk.Entry(params_frame, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", pady=5, padx=(10, 0))
        
        coord_frame = ttk.Frame(params_frame)
        coord_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        
        ttk.Label(coord_frame, text="X:").grid(row=0, column=0)
        self.x_var = tk.StringVar(value="0")
        ttk.Entry(coord_frame, textvariable=self.x_var, width=8).grid(row=0, column=1, padx=(5, 15))
        
        ttk.Label(coord_frame, text="Y:").grid(row=0, column=2)
        self.y_var = tk.StringVar(value="0")
        ttk.Entry(coord_frame, textvariable=self.y_var, width=8).grid(row=0, column=3, padx=(5, 15))
        
        ttk.Label(coord_frame, text="Z:").grid(row=0, column=4)
        self.z_var = tk.StringVar(value="0.5")
        ttk.Entry(coord_frame, textvariable=self.z_var, width=8).grid(row=0, column=5, padx=(5, 0))
        
        # Quick position buttons
        quick_frame = ttk.Frame(params_frame)
        quick_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        
        ttk.Label(quick_frame, text="Quick:").pack(side=tk.LEFT)
        ttk.Button(quick_frame, text="Origin", width=8,
                  command=lambda: self.set_position(0, 0, 0.5)).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="+5m X", width=8,
                  command=lambda: self.offset_position(5, 0, 0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(quick_frame, text="+5m Y", width=8,
                  command=lambda: self.offset_position(0, 5, 0)).pack(side=tk.LEFT, padx=2)
        
        # Spawn button
        self.spawn_button = ttk.Button(params_frame, text="Spawn Drone",
                                       command=self.spawn_drone, state='disabled',
                                       style='Success.TButton')
        self.spawn_button.grid(row=3, column=0, columnspan=2, pady=(15, 5), sticky="ew")
        
        # Spawned drones list
        spawned_frame = ttk.LabelFrame(right_frame, text="Spawned Drones", padding="10")
        spawned_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        spawned_frame.columnconfigure(0, weight=1)
        
        self.spawned_listbox = tk.Listbox(spawned_frame, height=4, font=('Consolas', 9))
        self.spawned_listbox.grid(row=0, column=0, sticky="ew")
        
    def on_state_changed(self, event: str):
        if event in ['world_changed', 'gazebo_state_changed']:
            self.after(0, self.update_world_status)
        elif event == 'drones_cleared':
            self.after(0, lambda: self.spawned_listbox.delete(0, tk.END))
            self.spawn_counter = 1
            
    def update_world_status(self):
        if self.state.current_world and self.state.is_gazebo_running:
            self.world_status_var.set(self.state.current_world)
            self.world_status_label.config(style='StatusGreen.TLabel')
            self.spawn_button.config(state='normal')
        else:
            self.world_status_var.set("No environment running")
            self.world_status_label.config(style='StatusRed.TLabel')
            self.spawn_button.config(state='disabled')
            
    def scan_models(self):
        self.models.clear()
        self.model_listbox.delete(0, tk.END)
        
        for model_dir in self.model_directories:
            path = model_dir['path']
            if not path.exists():
                continue
                
            if model_dir['type'] == 'flat':
                for sdf_file in path.glob("*.sdf"):
                    self.models.append({
                        'name': sdf_file.stem,
                        'path': str(sdf_file),
                        'source': model_dir['name']
                    })
            else:
                for model_folder in path.iterdir():
                    if model_folder.is_dir():
                        model_sdf = model_folder / "model.sdf"
                        if model_sdf.exists():
                            self.models.append({
                                'name': model_folder.name,
                                'path': str(model_sdf),
                                'source': model_dir['name']
                            })
                            
        self.models.sort(key=lambda x: x['name'].lower())
        
        for model in self.models:
            self.model_listbox.insert(tk.END, f"{model['name']} [{model['source'][0]}]")
            
    def on_model_selected(self, event=None):
        selection = self.model_listbox.curselection()
        if not selection:
            return
        model = self.models[selection[0]]
        self.model_info_var.set(f"{model['name']}\nSource: {model['source']}")
        self.name_var.set(f"{model['name']}_{self.spawn_counter}")
        self.load_preview(model['name'])
        
    def load_preview(self, model_name: str):
        if not PIL_AVAILABLE:
            self.preview_label.config(image='', text="Install Pillow for previews")
            return
            
        for preview_dir in self.preview_directories:
            for ext in ['.jpg', '.jpeg', '.png']:
                preview_path = preview_dir / f"{model_name}{ext}"
                if preview_path.exists():
                    try:
                        img = Image.open(preview_path)
                        ratio = min(300 / img.width, 200 / img.height)
                        img = img.resize((int(img.width * ratio), int(img.height * ratio)),
                                        Image.Resampling.LANCZOS)
                        self.current_preview = ImageTk.PhotoImage(img)
                        self.preview_label.config(image=self.current_preview, text='')
                        return
                    except Exception:
                        pass
                        
        self.preview_label.config(image='', text="No preview available")
        
    def set_position(self, x, y, z):
        self.x_var.set(str(x))
        self.y_var.set(str(y))
        self.z_var.set(str(z))
        
    def offset_position(self, dx, dy, dz):
        try:
            x = float(self.x_var.get()) + dx
            y = float(self.y_var.get()) + dy
            z = float(self.z_var.get()) + dz
            self.set_position(x, y, z)
        except ValueError:
            self.set_position(dx, dy, dz)
        
    def spawn_drone(self):
        if not self.state.current_world:
            messagebox.showerror("No World", "Launch an environment first")
            return
            
        selection = self.model_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Model", "Select a model first")
            return
            
        model = self.models[selection[0]]
        drone_name = self.name_var.get().strip()
        
        if not drone_name:
            messagebox.showwarning("No Name", "Enter a drone name")
            return
            
        try:
            x = float(self.x_var.get())
            y = float(self.y_var.get())
            z = float(self.z_var.get())
        except ValueError:
            messagebox.showerror("Invalid Coords", "Coordinates must be numbers")
            return
            
        cmd = [
            'gz', 'service',
            '-s', f'/world/{self.state.current_world}/create',
            '--reqtype', 'gz.msgs.EntityFactory',
            '--reptype', 'gz.msgs.Boolean',
            '--timeout', '1000',
            '--req', f'sdf_filename: "{model["path"]}", name: "{drone_name}", pose: {{position: {{x: {x}, y: {y}, z: {z}}}}}'
        ]
        
        thread = threading.Thread(target=self._execute_spawn,
                                 args=(cmd, drone_name, model['name'], x, y, z))
        thread.daemon = True
        thread.start()
        
    def _execute_spawn(self, cmd, drone_name, model_name, x, y, z):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                drone_info = {
                    'name': drone_name,
                    'model': model_name,
                    'position': (x, y, z)
                }
                self.state.add_drone(drone_info)
                self.after(0, lambda: self._on_spawn_success(drone_name))
            else:
                error_msg = result.stderr or "Unknown error"
                self.after(0, lambda: messagebox.showerror("Spawn Failed", error_msg))
                
        except subprocess.TimeoutExpired:
            self.after(0, lambda: messagebox.showerror("Timeout", "Spawn command timed out"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
            
    def _on_spawn_success(self, drone_name):
        self.spawned_listbox.insert(tk.END, drone_name)
        self.spawn_counter += 1
        
        selection = self.model_listbox.curselection()
        if selection:
            model = self.models[selection[0]]
            self.name_var.set(f"{model['name']}_{self.spawn_counter}")
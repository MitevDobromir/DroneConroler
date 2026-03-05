"""
environment_tab.py - Tab for launching Gazebo environments
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import os
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

# Try to import PIL for image preview
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from .global_state import GlobalState
from .theme import get_terminal_colors, COLORS


class EnvironmentTab(ttk.Frame):
    """Tab for launching Gazebo environments"""
    
    def __init__(self, parent, state: GlobalState):
        super().__init__(parent, padding="10")
        self.state = state
        
        # Paths
        self.worlds_path = state.ros2_tools_path / "Worlds"
        self.scripts_path = state.ros2_tools_path / "Scripts"
        self.previews_path = self.worlds_path / "previews"
        self.launch_script = self.scripts_path / "launch_env.sh"
        
        # Worlds list
        self.worlds = []
        self.current_preview = None
        
        self.setup_gui()
        self.scan_worlds()
        
    def setup_gui(self):
        """Setup the environment tab GUI"""
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)
        
        # Left panel - World selection
        left_frame = ttk.LabelFrame(self, text="Available Worlds", padding="10")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)
        
        # World listbox
        list_frame = ttk.Frame(left_frame)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.world_listbox = tk.Listbox(list_frame, font=('Consolas', 11),
                                        selectmode=tk.SINGLE, exportselection=False)
        self.world_listbox.grid(row=0, column=0, sticky="nsew")
        self.world_listbox.bind('<<ListboxSelect>>', self.on_world_selected)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                 command=self.world_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.world_listbox.config(yscrollcommand=scrollbar.set)
        
        ttk.Button(left_frame, text="Refresh",
                  command=self.scan_worlds).grid(row=1, column=0, pady=(10, 0), sticky="ew")
        
        # Right panel - Preview and controls
        right_frame = ttk.Frame(self)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        # Preview frame
        preview_frame = ttk.LabelFrame(right_frame, text="World Preview", padding="10")
        preview_frame.grid(row=0, column=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)
        
        self.preview_label = ttk.Label(preview_frame, text="Select a world",
                                       anchor=tk.CENTER,
                                       foreground=COLORS['fg_muted'])
        self.preview_label.grid(row=0, column=0, sticky="nsew")
        
        self.world_info_var = tk.StringVar(value="No world selected")
        ttk.Label(preview_frame, textvariable=self.world_info_var,
                 wraplength=350).grid(row=1, column=0, pady=(10, 0), sticky="ew")
        
        # Control buttons
        control_frame = ttk.LabelFrame(right_frame, text="Controls", padding="10")
        control_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        control_frame.columnconfigure(0, weight=1)
        control_frame.columnconfigure(1, weight=1)
        
        self.launch_button = ttk.Button(control_frame, text="▶  Launch Environment",
                                        command=self.launch_environment,
                                        style='Accent.TButton')
        self.launch_button.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ew")
        
        self.stop_button = ttk.Button(control_frame, text="⏹  Stop Gazebo",
                                      command=self.stop_gazebo, state='disabled',
                                      style='Danger.TButton')
        self.stop_button.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="ew")
        
        # Terminal output
        terminal_frame = ttk.LabelFrame(right_frame, text="Output", padding="10")
        terminal_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        terminal_frame.columnconfigure(0, weight=1)
        
        tc = get_terminal_colors()
        self.terminal_text = scrolledtext.ScrolledText(
            terminal_frame, height=6,
            font=('Consolas', 9), state='disabled',
            bg=tc['bg'], fg=tc['fg'],
            selectbackground=tc['select_bg'],
            selectforeground=tc['select_fg'],
            insertbackground=tc['fg'],
            relief='flat', borderwidth=0)
        self.terminal_text.grid(row=0, column=0, sticky="ew")
        
    def scan_worlds(self):
        self.worlds.clear()
        self.world_listbox.delete(0, tk.END)
        
        if not self.worlds_path.exists():
            self.log("[WARN] Worlds directory not found")
            return
            
        for sdf_file in sorted(self.worlds_path.glob("*.sdf")):
            world_name = self.parse_world_name(sdf_file)
            self.worlds.append({
                'name': sdf_file.stem,
                'world_name': world_name,
                'file': sdf_file.name,
                'path': sdf_file
            })
            self.world_listbox.insert(tk.END, sdf_file.stem)
            
        self.log(f"[INFO] Found {len(self.worlds)} world(s)")
        
    def parse_world_name(self, sdf_path: Path) -> Optional[str]:
        try:
            tree = ET.parse(sdf_path)
            root = tree.getroot()
            world_elem = root.find('.//world')
            if world_elem is not None:
                return world_elem.get('name')
        except Exception:
            pass
        return None
        
    def on_world_selected(self, event=None):
        selection = self.world_listbox.curselection()
        if not selection:
            return
        world = self.worlds[selection[0]]
        self.world_info_var.set(f"File: {world['file']}\nWorld name: {world['world_name'] or 'Unknown'}")
        self.load_preview(world['name'])
        
    def load_preview(self, world_name: str):
        if not PIL_AVAILABLE:
            self.preview_label.config(image='', text="Install Pillow for previews")
            return
            
        for ext in ['.jpg', '.jpeg', '.png']:
            preview_path = self.previews_path / f"{world_name}{ext}"
            if preview_path.exists():
                try:
                    img = Image.open(preview_path)
                    ratio = min(400 / img.width, 280 / img.height)
                    img = img.resize((int(img.width * ratio), int(img.height * ratio)),
                                    Image.Resampling.LANCZOS)
                    self.current_preview = ImageTk.PhotoImage(img)
                    self.preview_label.config(image=self.current_preview, text='')
                    return
                except Exception:
                    pass
                    
        self.preview_label.config(image='', text=f"No preview\n\nAdd: {self.previews_path}/{world_name}.jpg")
        
    def launch_environment(self):
        selection = self.world_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a world")
            return
            
        if self.state.is_gazebo_running:
            messagebox.showwarning("Already Running", "Stop current environment first")
            return
            
        world = self.worlds[selection[0]]
        
        self.log(f"\n{'='*40}")
        self.log(f"[LAUNCH] {world['name']}")
        self.log(f"[WORLD] {world['world_name']}")
        self.log(f"{'='*40}")
        
        self.state.set_world(world['world_name'], world['file'])
        self.state.clear_drones()
        
        thread = threading.Thread(target=self._run_launch, args=(world,))
        thread.daemon = True
        thread.start()
        
    def _run_launch(self, world: Dict):
        try:
            self.state.set_gazebo_running(True)
            self.after(0, self._update_ui_running)
            
            # Clean snap paths from LD_LIBRARY_PATH to prevent GUI crashes
            # (Ubuntu 24.04 + VirtualBox snap libpthread conflict)
            snap_clean = (
                'export LD_LIBRARY_PATH='
                '$(echo "$LD_LIBRARY_PATH" | tr \':\' \'\\n\' | '
                'grep -v \'/snap/\' | tr \'\\n\' \':\' | sed \'s/:$//\') && '
            )
            cmd = f'bash -c "{snap_clean}source {self.launch_script} {world["file"]}"'
            
            self.state.gazebo_process = subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                preexec_fn=os.setsid
            )
            
            for line in iter(self.state.gazebo_process.stdout.readline, ''):
                if line:
                    self.after(0, lambda l=line: self.log(l.rstrip()))
                    
            self.state.gazebo_process.wait()
            
        except Exception as e:
            self.after(0, lambda: self.log(f"[ERROR] {e}"))
        finally:
            self.state.set_gazebo_running(False)
            self.state.set_world(None, None)
            self.after(0, self._update_ui_stopped)
            
    def _update_ui_running(self):
        self.launch_button.config(state='disabled')
        self.stop_button.config(state='normal')
        
    def _update_ui_stopped(self):
        self.launch_button.config(state='normal')
        self.stop_button.config(state='disabled')
        
    def stop_gazebo(self):
        if self.state.gazebo_process:
            self.log("[STOP] Terminating Gazebo...")
            try:
                import signal
                os.killpg(os.getpgid(self.state.gazebo_process.pid), signal.SIGTERM)
            except Exception:
                pass
        subprocess.run(['pkill', '-f', 'gz sim'], capture_output=True)
        
    def log(self, message: str):
        self.terminal_text.config(state='normal')
        self.terminal_text.insert(tk.END, message + '\n')
        self.terminal_text.see(tk.END)
        self.terminal_text.config(state='disabled')
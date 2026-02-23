#!/usr/bin/env python3
"""
main.py - Drone Control Center main application
Entry point for the tabbed GUI application
"""
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os

from .global_state import STATE
from .theme import apply_theme, COLORS
from .environment_tab import EnvironmentTab
from .spawner_tab import SpawnerTab
from .controller_tab import ControllerTab
from .driver_tab import DriverTab


class DroneControlCenter:
    """Main application with tabbed interface"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Drone Control Center")
        self.root.geometry("950x750")
        self.root.minsize(850, 650)
        
        # Use global state
        self.state = STATE
        
        # Apply dark theme before building widgets
        apply_theme(self.root)
        
        self.setup_gui()
        
    def setup_gui(self):
        """Setup main GUI with tabs"""
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Main frame
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Header with global status
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        header_frame.columnconfigure(1, weight=1)
        
        # Title
        ttk.Label(header_frame, text="Drone Control Center",
                 style='Title.TLabel').grid(row=0, column=0, sticky="w")
        
        # Global status indicators
        status_frame = ttk.Frame(header_frame)
        status_frame.grid(row=0, column=1, sticky="e")
        
        # Environment status
        ttk.Label(status_frame, text="Environment:").pack(side=tk.LEFT)
        self.global_world_var = tk.StringVar(value="None")
        self.global_world_label = ttk.Label(status_frame, textvariable=self.global_world_var,
                                            style='StatusGray.TLabel')
        self.global_world_label.pack(side=tk.LEFT, padx=(5, 15))
        
        # Driver status
        ttk.Label(status_frame, text="Driver:").pack(side=tk.LEFT)
        self.global_driver_var = tk.StringVar(value="Stopped")
        self.global_driver_label = ttk.Label(status_frame, textvariable=self.global_driver_var,
                                             style='StatusGray.TLabel')
        self.global_driver_label.pack(side=tk.LEFT, padx=(5, 15))
        
        # Drones count
        ttk.Label(status_frame, text="Drones:").pack(side=tk.LEFT)
        self.global_drones_var = tk.StringVar(value="0")
        ttk.Label(status_frame, textvariable=self.global_drones_var,
                 style='Status.TLabel').pack(side=tk.LEFT, padx=(5, 0))
        
        # Notebook (tabbed interface)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        
        # Create tabs
        self.env_tab = EnvironmentTab(self.notebook, self.state)
        self.spawner_tab = SpawnerTab(self.notebook, self.state)
        self.driver_tab = DriverTab(self.notebook, self.state)
        self.controller_tab = ControllerTab(self.notebook, self.state)
        
        # Add tabs to notebook
        self.notebook.add(self.env_tab, text="  Environment  ")
        self.notebook.add(self.spawner_tab, text="  Spawn Drones  ")
        self.notebook.add(self.driver_tab, text="  Drivers  ")
        self.notebook.add(self.controller_tab, text="  Controller  ")
        
        # Listen for state changes to update header
        self.state.add_listener(self.on_state_changed)
        
    def on_state_changed(self, event: str):
        """Update global status display based on state changes"""
        if event in ['world_changed', 'gazebo_state_changed']:
            self._update_world_status()
                
        if event in ['drone_spawned', 'drones_cleared', 'drone_removed']:
            self._update_drone_count()
            
        if event == 'driver_state_changed':
            self._update_driver_status()
            
    def _update_world_status(self):
        if self.state.current_world and self.state.is_gazebo_running:
            self.global_world_var.set(self.state.current_world)
            self.global_world_label.config(style='StatusGreen.TLabel')
        else:
            self.global_world_var.set("None")
            self.global_world_label.config(style='StatusGray.TLabel')
            
    def _update_drone_count(self):
        self.global_drones_var.set(str(len(self.state.spawned_drones)))
        
    def _update_driver_status(self):
        if self.driver_tab.is_driver_running:
            self.global_driver_var.set("Running")
            self.global_driver_label.config(style='StatusGreen.TLabel')
        else:
            self.global_driver_var.set("Stopped")
            self.global_driver_label.config(style='StatusGray.TLabel')
            
    def on_closing(self):
        running = []
        if self.state.is_gazebo_running:
            running.append("Gazebo")
        if self.driver_tab.is_driver_running:
            running.append("Driver")
            
        if running:
            names = " and ".join(running)
            if messagebox.askyesno("Confirm Exit",
                                   f"{names} still running.\nStop and exit?"):
                self._stop_all()
                self.root.after(500, self.root.destroy)
            return
        self.root.destroy()
        
    def _stop_all(self):
        if self.driver_tab.is_driver_running:
            self.driver_tab.stop_driver()
        if self.state.gazebo_process:
            try:
                import signal
                os.killpg(os.getpgid(self.state.gazebo_process.pid), signal.SIGTERM)
            except Exception:
                pass
        subprocess.run(['pkill', '-f', 'gz sim'], capture_output=True)


def main():
    """Application entry point"""
    root = tk.Tk()
    app = DroneControlCenter(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
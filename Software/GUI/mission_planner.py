#!/usr/bin/env python3
"""
mission_planner.py - GUI-based drone mission planner
"""
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sys
import os
import threading

# Add parent directory to path to import from Common
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Common.flight_controller import DroneController

class MissionPlannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Drone Mission Planner")
        self.root.geometry("900x650")
        
        self.mission_steps = []
        self.drone = None
        self.is_running = False
        self.gps_update_active = False
        
        # Step type definitions
        self.step_types = {
            'Land': {'params': []},
            'Move': {'params': [
                {'name': 'x', 'label': 'X (m, forward+)', 'default': '0', 'type': 'float', 'allow_negative': True, 'min': -100, 'max': 100},
                {'name': 'y', 'label': 'Y (m, right+)', 'default': '0', 'type': 'float', 'allow_negative': True, 'min': -100, 'max': 100},
                {'name': 'speed', 'label': 'Speed (m/s)', 'default': '1.0', 'type': 'float', 'min': 0.1, 'max': 10.0}
            ]},
            'Takeoff': {'params': [{'name': 'altitude', 'label': 'Altitude (m)', 'default': '5', 'type': 'float', 'min': 1, 'max': 50}]}
        }
        
        self.setup_gui()
        
    def setup_gui(self):
        """Setup the GUI layout"""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Title
        title = ttk.Label(main_frame, text="Drone Mission Planner", 
                         font=('Arial', 16, 'bold'))
        title.grid(row=0, column=0, columnspan=2, pady=10)
        
        # GPS Display Frame
        self.setup_gps_display(main_frame)
        
        # Left panel - Step controls
        control_frame = ttk.LabelFrame(main_frame, text="Add Step", padding="10")
        control_frame.grid(row=2, column=0, sticky=(tk.N, tk.W, tk.E), padx=(0, 5))
        
        # Step type selection
        ttk.Label(control_frame, text="Step Type:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.step_type_var = tk.StringVar()
        self.step_type_combo = ttk.Combobox(control_frame, textvariable=self.step_type_var, 
                                            state='readonly', width=25)
        self.step_type_combo['values'] = sorted(self.step_types.keys())
        self.step_type_combo.current(0)
        self.step_type_combo.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        self.step_type_combo.bind('<<ComboboxSelected>>', self.on_step_type_changed)
        
        ttk.Separator(control_frame, orient=tk.HORIZONTAL).grid(row=2, column=0, 
                                                                sticky=(tk.W, tk.E), pady=10)
        
        # Parameters frame (dynamic based on step type)
        self.params_frame = ttk.Frame(control_frame)
        self.params_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        self.params_frame.columnconfigure(1, weight=1)
        
        self.param_widgets = {}
        
        # Add step button
        ttk.Button(control_frame, text="Add Step", 
                  command=self.add_step).grid(row=4, column=0, pady=10, sticky=(tk.W, tk.E))
        
        # Initialize parameter fields
        self.on_step_type_changed()
        
        # Right panel - Mission steps
        mission_frame = ttk.LabelFrame(main_frame, text="Mission Steps", padding="10")
        mission_frame.grid(row=2, column=1, sticky=(tk.N, tk.S, tk.W, tk.E))
        mission_frame.rowconfigure(0, weight=1)
        mission_frame.columnconfigure(0, weight=1)
        
        # Mission listbox
        self.mission_listbox = tk.Listbox(mission_frame, height=15, font=('Courier', 10))
        self.mission_listbox.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        
        scrollbar = ttk.Scrollbar(mission_frame, orient=tk.VERTICAL, 
                                 command=self.mission_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.mission_listbox.config(yscrollcommand=scrollbar.set)
        
        # Button frame for mission list controls
        button_frame = ttk.Frame(mission_frame)
        button_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky=(tk.W, tk.E))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        
        # Remove selected step button
        ttk.Button(button_frame, text="Remove Selected Step", 
                  command=self.remove_step).grid(row=0, column=0, padx=(0, 2), sticky=(tk.W, tk.E))
        
        # Clear all steps button
        ttk.Button(button_frame, text="Clear All Steps", 
                  command=self.clear_steps).grid(row=0, column=1, padx=(2, 0), sticky=(tk.W, tk.E))
        
        # Bottom panel - Run controls and status
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=10)
        bottom_frame.columnconfigure(0, weight=1)
        bottom_frame.columnconfigure(1, weight=1)
        
        # Connect button
        self.connect_button = ttk.Button(bottom_frame, text="Connect to Drone", 
                                         command=self.connect_drone)
        self.connect_button.grid(row=0, column=0, pady=5, padx=(0, 5), sticky=(tk.W, tk.E))
        
        # Run button
        self.run_button = ttk.Button(bottom_frame, text="Run Mission", 
                                     command=self.run_mission)
        self.run_button.grid(row=0, column=1, pady=5, padx=(5, 0), sticky=(tk.W, tk.E))
        
        # Status area
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.S))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_text = scrolledtext.ScrolledText(status_frame, height=8, 
                                                     state='disabled', 
                                                     font=('Courier', 9))
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
    
    def setup_gps_display(self, parent):
        """Setup the GPS coordinates display frame"""
        gps_frame = ttk.LabelFrame(parent, text="GPS Coordinates", padding="10")
        gps_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        gps_frame.columnconfigure(1, weight=1)
        gps_frame.columnconfigure(3, weight=1)
        gps_frame.columnconfigure(5, weight=1)
        
        # Status indicator
        ttk.Label(gps_frame, text="Status:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.gps_status_var = tk.StringVar(value="Disconnected")
        self.gps_status_label = ttk.Label(gps_frame, textvariable=self.gps_status_var,
                                          font=('Arial', 10, 'bold'), foreground='red')
        self.gps_status_label.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        
        # Latitude
        ttk.Label(gps_frame, text="Lat:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.lat_var = tk.StringVar(value="---.------")
        ttk.Label(gps_frame, textvariable=self.lat_var, font=('Courier', 11),
                 width=12).grid(row=0, column=3, sticky=tk.W, padx=(0, 20))
        
        # Longitude
        ttk.Label(gps_frame, text="Lon:").grid(row=0, column=4, sticky=tk.W, padx=(0, 5))
        self.lon_var = tk.StringVar(value="---.------")
        ttk.Label(gps_frame, textvariable=self.lon_var, font=('Courier', 11),
                 width=12).grid(row=0, column=5, sticky=tk.W, padx=(0, 20))
        
        # Altitude
        ttk.Label(gps_frame, text="Alt:").grid(row=0, column=6, sticky=tk.W, padx=(0, 5))
        self.alt_var = tk.StringVar(value="---.- m")
        ttk.Label(gps_frame, textvariable=self.alt_var, font=('Courier', 11),
                 width=10).grid(row=0, column=7, sticky=tk.W)
    
    def connect_drone(self):
        """Connect to the drone and start GPS updates"""
        if self.drone is not None:
            # Disconnect
            self.stop_gps_updates()
            self.drone = None
            self.connect_button.config(text="Connect to Drone")
            self.gps_status_var.set("Disconnected")
            self.gps_status_label.config(foreground='red')
            self.lat_var.set("---.------")
            self.lon_var.set("---.------")
            self.alt_var.set("---.- m")
            self.add_status("Disconnected from drone")
            return
        
        try:
            self.add_status("Connecting to drone...")
            self.drone = DroneController()
            self.connect_button.config(text="Disconnect")
            self.gps_status_var.set("Connected")
            self.gps_status_label.config(foreground='green')
            self.add_status("Connected to drone successfully!")
            
            # Start GPS updates
            self.start_gps_updates()
            
        except Exception as e:
            self.add_status(f"Connection failed: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect: {e}")
            self.drone = None
    
    def start_gps_updates(self):
        """Start periodic GPS coordinate updates"""
        self.gps_update_active = True
        self.update_gps_display()
    
    def stop_gps_updates(self):
        """Stop GPS coordinate updates"""
        self.gps_update_active = False
    
    def update_gps_display(self):
        """Update GPS coordinates display"""
        if not self.gps_update_active or self.drone is None:
            return
        
        # Run the blocking MAVLink call in a thread to avoid freezing GUI
        def fetch_and_update():
            try:
                location = self.drone.get_location()
                
                # Schedule GUI update on main thread
                if location:
                    self.root.after(0, lambda: self._update_gps_labels(location))
                else:
                    self.root.after(0, lambda: self._set_gps_status("No GPS", "orange"))
                    
            except Exception as e:
                self.root.after(0, lambda: self._set_gps_status("Error", "red"))
            
            # Schedule next update
            if self.gps_update_active:
                self.root.after(500, self.update_gps_display)
        
        thread = threading.Thread(target=fetch_and_update, daemon=True)
        thread.start()
    
    def _update_gps_labels(self, location):
        """Update GPS labels on main thread"""
        self.lat_var.set(f"{location['lat']:11.6f}")
        self.lon_var.set(f"{location['lon']:11.6f}")
        # Use relative_alt (above ground) for more useful reading
        self.alt_var.set(f"{location['relative_alt']:6.1f} m")
        self.gps_status_var.set("GPS Lock")
        self.gps_status_label.config(foreground='green')
    
    def _set_gps_status(self, status, color):
        """Set GPS status on main thread"""
        self.gps_status_var.set(status)
        self.gps_status_label.config(foreground=color)
        
    def on_step_type_changed(self, event=None):
        """Update parameter inputs based on selected step type"""
        # Clear existing parameter widgets
        for widget in self.params_frame.winfo_children():
            widget.destroy()
        self.param_widgets.clear()
        
        # Get selected step type
        step_type = self.step_type_var.get()
        params = self.step_types[step_type]['params']
        
        # Create parameter inputs
        if params:
            ttk.Label(self.params_frame, text="Parameters:", 
                     font=('Arial', 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))
            
            for i, param in enumerate(params, start=1):
                # Build label with range info
                label_text = param['label']
                min_val = param.get('min')
                max_val = param.get('max')
                if min_val is not None and max_val is not None:
                    label_text += f" [{min_val} to {max_val}]"
                
                # Label (left column)
                ttk.Label(self.params_frame, text=label_text + ":").grid(
                    row=i, column=0, sticky=tk.W, pady=2, padx=(0, 10))
                
                # Entry (right column)
                entry = ttk.Entry(self.params_frame, width=15)
                entry.insert(0, param['default'])
                entry.grid(row=i, column=1, sticky=(tk.W, tk.E), pady=2)
                
                self.param_widgets[param['name']] = {
                    'widget': entry,
                    'type': param['type']
                }
        else:
            ttk.Label(self.params_frame, text="No parameters required", 
                     font=('Arial', 9, 'italic')).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)
        
    def add_step(self):
        """Add selected step type to mission"""
        step_type = self.step_type_var.get()
        step = {'type': step_type.lower()}
        
        # Get parameters
        params = self.step_types[step_type]['params']
        try:
            param_values = {}
            for param in params:
                param_name = param['name']
                value = self.param_widgets[param_name]['widget'].get()
                param_type = self.param_widgets[param_name]['type']
                
                # Validate and convert
                if param_type == 'float':
                    value = float(value)
                    # Check min/max if specified
                    min_val = param.get('min')
                    max_val = param.get('max')
                    if min_val is not None and value < min_val:
                        messagebox.showerror("Error", f"{param['label']} must be at least {min_val}")
                        return
                    if max_val is not None and value > max_val:
                        messagebox.showerror("Error", f"{param['label']} must be at most {max_val}")
                        return
                    # Legacy check for params without min/max that don't allow negative
                    if min_val is None and not param.get('allow_negative', False) and value <= 0:
                        messagebox.showerror("Error", f"{param['label']} must be greater than 0")
                        return
                elif param_type == 'int':
                    value = int(value)
                    min_val = param.get('min')
                    max_val = param.get('max')
                    if min_val is not None and value < min_val:
                        messagebox.showerror("Error", f"{param['label']} must be at least {min_val}")
                        return
                    if max_val is not None and value > max_val:
                        messagebox.showerror("Error", f"{param['label']} must be at most {max_val}")
                        return
                    
                param_values[param_name] = value
                step[param_name] = value
            
            # Add step to mission
            self.mission_steps.append(step)
            
            # Update display
            display_text = f"Step {len(self.mission_steps)}: {step_type}"
            if param_values:
                param_str = ", ".join([f"{k}={v}" for k, v in param_values.items()])
                display_text += f" ({param_str})"
            
            self.mission_listbox.insert(tk.END, display_text)
            self.add_status(f"Added: {display_text}")
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid parameter value: {e}")
            
    def add_status(self, message):
        """Add message to status window"""
        self.status_text.config(state='normal')
        self.status_text.insert(tk.END, message + '\n')
        self.status_text.see(tk.END)
        self.status_text.config(state='disabled')
            
    def remove_step(self):
        """Remove selected step from mission"""
        selection = self.mission_listbox.curselection()
        if selection:
            index = selection[0]
            self.mission_steps.pop(index)
            self.mission_listbox.delete(index)
            self.refresh_mission_list()
            self.add_status(f"Removed step {index + 1}")
        else:
            messagebox.showwarning("Warning", "No step selected")
            
    def clear_steps(self):
        """Clear all mission steps"""
        if self.mission_steps:
            if messagebox.askyesno("Confirm", "Clear all mission steps?"):
                self.mission_steps.clear()
                self.mission_listbox.delete(0, tk.END)
                self.add_status("All steps cleared")
        else:
            messagebox.showinfo("Info", "No steps to clear")
            
    def refresh_mission_list(self):
        """Refresh the mission list display"""
        self.mission_listbox.delete(0, tk.END)
        for i, step in enumerate(self.mission_steps, 1):
            step_type = step['type'].capitalize()
            display_text = f"Step {i}: {step_type}"
            
            # Add parameters to display
            param_str = []
            for key, value in step.items():
                if key != 'type':
                    param_str.append(f"{key}={value}")
            
            if param_str:
                display_text += f" ({', '.join(param_str)})"
                
            self.mission_listbox.insert(tk.END, display_text)
                
    def run_mission(self):
        """Run the mission in a separate thread"""
        if not self.mission_steps:
            messagebox.showwarning("Warning", "No mission steps added")
            return
            
        if self.is_running:
            messagebox.showwarning("Warning", "Mission is already running")
            return
            
        # Run in thread to prevent GUI freezing
        thread = threading.Thread(target=self.execute_mission)
        thread.daemon = True
        thread.start()
        
    def execute_mission(self):
        """Execute the mission steps"""
        self.is_running = True
        self.run_button.config(state='disabled')
        self.add_status("\n" + "=" * 50)
        self.add_status("Starting mission...")
        self.add_status("=" * 50)
        
        try:
            # Connect if not already connected
            if self.drone is None:
                self.add_status("[SETUP] Connecting to drone...")
                self.drone = DroneController()
                self.root.after(0, lambda: self.connect_button.config(text="Disconnect"))
                self.root.after(0, lambda: self.gps_status_var.set("Connected"))
                self.root.after(0, lambda: self.gps_status_label.config(foreground='green'))
                self.start_gps_updates()
            
            self.add_status("[SETUP] Waiting for GPS lock...")
            if not self.drone.wait_for_gps():
                self.add_status("[ERROR] Setup failed: Could not get GPS lock")
                messagebox.showerror("Setup Error", "Failed to get GPS lock")
                return
                
            self.add_status("[SETUP] Setting GUIDED mode...")
            if not self.drone.set_mode('GUIDED'):
                self.add_status("[ERROR] Setup failed: Could not set GUIDED mode")
                messagebox.showerror("Setup Error", "Failed to set GUIDED mode")
                return
                
            self.add_status("[SETUP] Arming throttle...")
            if not self.drone.arm():
                self.add_status("[ERROR] Setup failed: Could not arm throttle")
                messagebox.showerror("Setup Error", "Failed to arm throttle")
                return
                
            self.add_status("[SETUP] Setup complete!")
            self.add_status("")
            
            # Execute mission steps
            for i, step in enumerate(self.mission_steps, 1):
                self.add_status(f"Executing Step {i}...")
                
                if step['type'] == 'takeoff':
                    altitude = step['altitude']
                    self.add_status(f"  Taking off to {altitude}m...")
                    if not self.drone.takeoff(altitude):
                        self.add_status("[ERROR] Takeoff failed")
                        messagebox.showerror("Mission Error", f"Step {i} failed: Takeoff")
                        break
                
                elif step['type'] == 'move':
                    x = step['x']
                    y = step['y']
                    speed = step.get('speed', 1.0)
                    self.add_status(f"  Moving X={x}m, Y={y}m at {speed}m/s...")
                    if not self.drone.move_relative(x, y, speed):
                        self.add_status("[ERROR] Move failed")
                        messagebox.showerror("Mission Error", f"Step {i} failed: Move")
                        break
                        
                elif step['type'] == 'land':
                    self.add_status("  Landing...")
                    self.drone.land()
                    
                self.add_status(f"  Step {i} complete!")
                self.add_status("")
                
            self.add_status("=" * 50)
            self.add_status("Mission completed successfully!")
            self.add_status("=" * 50)
            messagebox.showinfo("Success", "Mission completed successfully!")
            
        except KeyboardInterrupt:
            self.add_status("\n[WARNING] Mission interrupted by user")
            if self.drone:
                self.drone.land()
        except Exception as e:
            self.add_status(f"\n[ERROR] {e}")
            messagebox.showerror("Error", f"Mission failed: {e}")
            if self.drone:
                self.drone.land()
        finally:
            self.is_running = False
            self.run_button.config(state='normal')

def main():
    root = tk.Tk()
    app = MissionPlannerGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
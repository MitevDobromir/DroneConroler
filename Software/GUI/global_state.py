"""
global_state.py - Shared state across all tabs
"""
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable


@dataclass
class GlobalState:
    """Shared state across all tabs"""
    
    # Paths
    ros2_tools_path: Path = field(default_factory=lambda: Path.home() / "ROS2_Tools")
    
    # Environment state
    current_world: Optional[str] = None
    current_world_file: Optional[str] = None
    gazebo_process: Optional[subprocess.Popen] = None
    is_gazebo_running: bool = False
    
    # Spawned drones
    spawned_drones: List[Dict] = field(default_factory=list)
    
    # Callbacks for state changes
    _listeners: List[Callable] = field(default_factory=list)
    
    def add_listener(self, callback: Callable):
        """Add a callback to be notified of state changes"""
        self._listeners.append(callback)
        
    def remove_listener(self, callback: Callable):
        """Remove a listener callback"""
        if callback in self._listeners:
            self._listeners.remove(callback)
        
    def notify_listeners(self, event: str):
        """Notify all listeners of a state change
        
        Events:
            - 'world_changed': World name changed
            - 'gazebo_state_changed': Gazebo started/stopped
            - 'drone_spawned': New drone was spawned
            - 'drones_cleared': All drones cleared
        """
        for callback in self._listeners:
            try:
                callback(event)
            except Exception as e:
                print(f"[GlobalState] Listener error: {e}")
                
    def set_world(self, world_name: Optional[str], world_file: Optional[str] = None):
        """Set the current world and notify listeners"""
        self.current_world = world_name
        self.current_world_file = world_file
        self.notify_listeners('world_changed')
        
    def set_gazebo_running(self, running: bool):
        """Set Gazebo running state and notify listeners"""
        self.is_gazebo_running = running
        self.notify_listeners('gazebo_state_changed')
        
    def add_drone(self, drone_info: Dict):
        """Add a spawned drone and notify listeners
        
        Args:
            drone_info: Dict with 'name', 'model', 'position' keys
        """
        self.spawned_drones.append(drone_info)
        self.notify_listeners('drone_spawned')
        
    def remove_drone(self, drone_name: str):
        """Remove a drone by name"""
        self.spawned_drones = [d for d in self.spawned_drones if d['name'] != drone_name]
        self.notify_listeners('drone_removed')
        
    def clear_drones(self):
        """Clear all spawned drones"""
        self.spawned_drones.clear()
        self.notify_listeners('drones_cleared')
        
    def get_drone(self, drone_name: str) -> Optional[Dict]:
        """Get drone info by name"""
        for drone in self.spawned_drones:
            if drone['name'] == drone_name:
                return drone
        return None


# Global state singleton instance
STATE = GlobalState()

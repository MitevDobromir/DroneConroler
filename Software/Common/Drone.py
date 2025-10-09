#!/usr/bin/env python3
"""
ArduPilot Formation Flying Controller
Professional drone swarm control using ArduPilot + MAVROS
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode, CommandTOL
import time
import threading
import math
from typing import List, Dict, Tuple

class FormationDrone:
    """Individual drone in formation"""
    
    def __init__(self, node, drone_id: str, namespace: str = ""):
        self.node = node
        self.drone_id = drone_id
        self.namespace = namespace
        
        # Publishers
        self.velocity_pub = node.create_publisher(
            Twist,
            f'{namespace}/mavros/setpoint_velocity/cmd_vel_unstamped',
            10
        )
        
        # Subscribers
        self.state_sub = node.create_subscription(
            State,
            f'{namespace}/mavros/state',
            self.state_callback,
            10
        )
        
        # Service clients
        self.arming_client = node.create_client(
            CommandBool,
            f'{namespace}/mavros/cmd/arming'
        )
        self.set_mode_client = node.create_client(
            SetMode,
            f'{namespace}/mavros/set_mode'
        )
        self.takeoff_client = node.create_client(
            CommandTOL,
            f'{namespace}/mavros/cmd/takeoff'
        )
        
        # State
        self.current_state = State()
        self.connected = False
        self.position = [0.0, 0.0, 0.0]  # x, y, z
        self.target_position = [0.0, 0.0, 0.0]
        
        self.node.get_logger().info(f'Formation drone {drone_id} initialized')
    
    def state_callback(self, msg):
        """Handle state updates"""
        self.current_state = msg
        if not self.connected and msg.connected:
            self.connected = True
            self.node.get_logger().info(f'✅ {self.drone_id} connected to ArduPilot')
        elif self.connected and not msg.connected:
            self.connected = False
            self.node.get_logger().warn(f'❌ {self.drone_id} lost connection')
    
    def set_mode(self, mode: str) -> bool:
        """Set flight mode"""
        if not self.connected:
            return False
            
        req = SetMode.Request()
        req.custom_mode = mode
        
        future = self.set_mode_client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)
        
        return future.result() and future.result().mode_sent
    
    def arm(self) -> bool:
        """Arm the drone"""
        if not self.connected:
            return False
            
        req = CommandBool.Request()
        req.value = True
        
        future = self.arming_client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)
        
        return future.result() and future.result().success
    
    def takeoff(self, altitude: float = 10.0) -> bool:
        """Takeoff to specified altitude"""
        # Set GUIDED mode
        if not self.set_mode('GUIDED'):
            return False
        
        time.sleep(0.5)
        
        # Arm
        if not self.arm():
            return False
        
        time.sleep(0.5)
        
        # Takeoff
        req = CommandTOL.Request()
        req.altitude = altitude
        
        future = self.takeoff_client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=10.0)
        
        return future.result() and future.result().success
    
    def send_velocity(self, vx: float, vy: float, vz: float, yaw_rate: float = 0.0):
        """Send velocity command"""
        twist = Twist()
        twist.linear.x = vx
        twist.linear.y = vy
        twist.linear.z = vz
        twist.angular.z = yaw_rate
        
        self.velocity_pub.publish(twist)
    
    def move_to_target(self, target: Tuple[float, float, float], speed: float = 1.0):
        """Move towards target position"""
        self.target_position = list(target)
        
        # Calculate direction vector
        dx = target[0] - self.position[0]
        dy = target[1] - self.position[1] 
        dz = target[2] - self.position[2]
        
        # Calculate distance
        distance = math.sqrt(dx*dx + dy*dy + dz*dz)
        
        if distance > 0.1:  # Move if not at target
            # Normalize and scale by speed
            vx = (dx / distance) * speed
            vy = (dy / distance) * speed
            vz = (dz / distance) * speed
            
            # Limit maximum velocity
            max_vel = 3.0
            vx = max(-max_vel, min(max_vel, vx))
            vy = max(-max_vel, min(max_vel, vy))
            vz = max(-max_vel, min(max_vel, vz))
            
            self.send_velocity(vx, vy, vz)
        else:
            self.send_velocity(0, 0, 0)  # Stop at target
    
    def stop(self):
        """Stop movement"""
        self.send_velocity(0, 0, 0)
    
    def land(self):
        """Land the drone"""
        self.set_mode('LAND')


class ArduPilotFormationController(Node):
    """Formation flying controller for ArduPilot drones"""
    
    def __init__(self):
        super().__init__('ardupilot_formation_controller')
        
        self.drones: List[FormationDrone] = []
        self.formation_active = False
        self.formation_center = [0.0, 0.0, 10.0]  # x, y, z
        
        # Formation patterns
        self.formations = {
            'line': self.line_formation,
            'triangle': self.triangle_formation,
            'square': self.square_formation,
            'circle': self.circle_formation,
            'diamond': self.diamond_formation
        }
        
        self.current_formation = 'line'
        self.formation_spacing = 5.0  # meters between drones
        
        # Control timer
        self.control_timer = self.create_timer(0.1, self.formation_control_loop)
        
        self.get_logger().info('ArduPilot Formation Controller initialized')
    
    def add_drone(self, drone_id: str, namespace: str = ""):
        """Add drone to formation"""
        drone = FormationDrone(self, drone_id, namespace)
        self.drones.append(drone)
        self.get_logger().info(f'Added {drone_id} to formation (total: {len(self.drones)})')
    
    def wait_for_connections(self, timeout: float = 30.0) -> bool:
        """Wait for all drones to connect"""
        self.get_logger().info('Waiting for drone connections...')
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            connected_count = sum(1 for drone in self.drones if drone.connected)
            
            if connected_count == len(self.drones):
                self.get_logger().info(f'✅ All {len(self.drones)} drones connected!')
                return True
                
            self.get_logger().info(f'Connected: {connected_count}/{len(self.drones)}')
            rclpy.spin_once(self, timeout_sec=1.0)
        
        self.get_logger().error('Timeout waiting for drone connections')
        return False
    
    def arm_all(self) -> bool:
        """Arm all drones"""
        self.get_logger().info('Arming all drones...')
        success_count = 0
        
        for drone in self.drones:
            if drone.arm():
                success_count += 1
                self.get_logger().info(f'✅ {drone.drone_id} armed')
            else:
                self.get_logger().error(f'❌ {drone.drone_id} failed to arm')
        
        return success_count == len(self.drones)
    
    def takeoff_formation(self, altitude: float = 10.0) -> bool:
        """Coordinated formation takeoff"""
        self.get_logger().info(f'Formation takeoff to {altitude}m...')
        
        # Start takeoff for all drones
        futures = []
        for i, drone in enumerate(self.drones):
            self.get_logger().info(f'Starting takeoff: {drone.drone_id}')
            
            # Stagger takeoff slightly to avoid prop wash
            if i > 0:
                time.sleep(1.0)
            
            success = drone.takeoff(altitude)
            if not success:
                self.get_logger().error(f'❌ {drone.drone_id} takeoff failed')
                return False
        
        # Wait for all to reach altitude
        self.get_logger().info('Waiting for formation to reach altitude...')
        time.sleep(10)  # Give time for takeoff
        
        self.get_logger().info('✅ Formation takeoff complete')
        return True
    
    def land_formation(self):
        """Coordinated formation landing"""
        self.get_logger().info('Formation landing...')
        
        for i, drone in enumerate(self.drones):
            self.get_logger().info(f'Landing: {drone.drone_id}')
            drone.land()
            
            # Stagger landing
            if i < len(self.drones) - 1:
                time.sleep(2.0)
        
        self.formation_active = False
        self.get_logger().info('✅ Formation landing complete')
    
    def set_formation(self, formation_name: str):
        """Set formation pattern"""
        if formation_name in self.formations:
            self.current_formation = formation_name
            self.get_logger().info(f'Formation set to: {formation_name}')
            return True
        else:
            self.get_logger().error(f'Unknown formation: {formation_name}')
            return False
    
    def line_formation(self) -> List[Tuple[float, float, float]]:
        """Generate line formation positions"""
        positions = []
        spacing = self.formation_spacing
        
        for i, drone in enumerate(self.drones):
            x = self.formation_center[0] + (i - len(self.drones)/2) * spacing
            y = self.formation_center[1]
            z = self.formation_center[2]
            positions.append((x, y, z))
        
        return positions
    
    def triangle_formation(self) -> List[Tuple[float, float, float]]:
        """Generate triangle formation positions"""
        positions = []
        spacing = self.formation_spacing
        
        if len(self.drones) >= 1:
            # Leader at front
            positions.append((
                self.formation_center[0],
                self.formation_center[1],
                self.formation_center[2]
            ))
        
        if len(self.drones) >= 2:
            # Left wing
            positions.append((
                self.formation_center[0] - spacing,
                self.formation_center[1] - spacing,
                self.formation_center[2]
            ))
        
        if len(self.drones) >= 3:
            # Right wing
            positions.append((
                self.formation_center[0] - spacing,
                self.formation_center[1] + spacing,
                self.formation_center[2]
            ))
        
        # Additional drones in second row
        for i in range(3, len(self.drones)):
            x = self.formation_center[0] - 2 * spacing
            y = self.formation_center[1] + (i - 3 - (len(self.drones)-4)/2) * spacing/2
            z = self.formation_center[2]
            positions.append((x, y, z))
        
        return positions
    
    def square_formation(self) -> List[Tuple[float, float, float]]:
        """Generate square formation positions"""
        positions = []
        spacing = self.formation_spacing
        
        # Square corners
        square_positions = [
            (spacing/2, spacing/2, 0),    # Front right
            (-spacing/2, spacing/2, 0),   # Back right
            (-spacing/2, -spacing/2, 0),  # Back left
            (spacing/2, -spacing/2, 0),   # Front left
        ]
        
        for i, drone in enumerate(self.drones):
            if i < 4:
                pos = square_positions[i]
                x = self.formation_center[0] + pos[0]
                y = self.formation_center[1] + pos[1]
                z = self.formation_center[2]
                positions.append((x, y, z))
            else:
                # Center additional drones
                x = self.formation_center[0]
                y = self.formation_center[1]
                z = self.formation_center[2] + (i - 3) * 2
                positions.append((x, y, z))
        
        return positions
    
    def circle_formation(self) -> List[Tuple[float, float, float]]:
        """Generate circle formation positions"""
        positions = []
        radius = self.formation_spacing
        
        for i, drone in enumerate(self.drones):
            angle = (2 * math.pi * i) / len(self.drones)
            x = self.formation_center[0] + radius * math.cos(angle)
            y = self.formation_center[1] + radius * math.sin(angle)
            z = self.formation_center[2]
            positions.append((x, y, z))
        
        return positions
    
    def diamond_formation(self) -> List[Tuple[float, float, float]]:
        """Generate diamond formation positions"""
        positions = []
        spacing = self.formation_spacing
        
        if len(self.drones) >= 1:
            # Leader at front
            positions.append((
                self.formation_center[0] + spacing,
                self.formation_center[1],
                self.formation_center[2]
            ))
        
        if len(self.drones) >= 2:
            # Left wing
            positions.append((
                self.formation_center[0],
                self.formation_center[1] - spacing,
                self.formation_center[2]
            ))
        
        if len(self.drones) >= 3:
            # Right wing
            positions.append((
                self.formation_center[0],
                self.formation_center[1] + spacing,
                self.formation_center[2]
            ))
        
        if len(self.drones) >= 4:
            # Tail
            positions.append((
                self.formation_center[0] - spacing,
                self.formation_center[1],
                self.formation_center[2]
            ))
        
        # Additional drones in center
        for i in range(4, len(self.drones)):
            x = self.formation_center[0]
            y = self.formation_center[1]
            z = self.formation_center[2] + (i - 3) * 2
            positions.append((x, y, z))
        
        return positions
    
    def formation_control_loop(self):
        """Main formation control loop"""
        if not self.formation_active or len(self.drones) == 0:
            return
        
        # Get target positions for current formation
        target_positions = self.formations[self.current_formation]()
        
        # Send commands to each drone
        for i, drone in enumerate(self.drones):
            if i < len(target_positions):
                drone.move_to_target(target_positions[i])
    
    def start_formation(self):
        """Start formation flying"""
        self.formation_active = True
        self.get_logger().info(f'✅ Formation flying started ({self.current_formation})')
    
    def stop_formation(self):
        """Stop formation flying"""
        self.formation_active = False
        for drone in self.drones:
            drone.stop()
        self.get_logger().info('🛑 Formation flying stopped')
    
    def move_formation(self, dx: float, dy: float, dz: float):
        """Move entire formation"""
        self.formation_center[0] += dx
        self.formation_center[1] += dy
        self.formation_center[2] += dz
        self.get_logger().info(f'Formation moved to: {self.formation_center}')
    
    def get_status(self) -> Dict:
        """Get formation status"""
        return {
            'active': self.formation_active,
            'formation': self.current_formation,
            'center': self.formation_center,
            'spacing': self.formation_spacing,
            'drones': len(self.drones),
            'connected': sum(1 for d in self.drones if d.connected)
        }


def main():
    """Main formation controller interface"""
    rclpy.init()
    
    try:
        # Create formation controller
        formation = ArduPilotFormationController()
        
        print("\n" + "="*60)
        print("🚁 ArduPilot Formation Flying Controller")
        print("="*60)
        
        # Add drones (modify these namespaces based on your setup)
        drone_configs = [
            ("leader", ""),      # No namespace = default MAVROS
            ("drone_1", ""),     # Add more as needed
            ("drone_2", ""),
        ]
        
        for drone_id, namespace in drone_configs:
            formation.add_drone(drone_id, namespace)
        
        # Wait for connections
        if not formation.wait_for_connections():
            return
        
        print("\n" + "="*60)
        print("FORMATION COMMANDS:")
        print("="*60)
        print("  arm        - Arm all drones")
        print("  takeoff    - Formation takeoff")
        print("  land       - Formation landing")
        print("  start      - Start formation flying")
        print("  stop       - Stop formation flying")
        print("  line       - Line formation")
        print("  triangle   - Triangle formation")
        print("  square     - Square formation")
        print("  circle     - Circle formation")
        print("  diamond    - Diamond formation")
        print("  forward    - Move formation forward")
        print("  backward   - Move formation backward")
        print("  left       - Move formation left")
        print("  right      - Move formation right")
        print("  up         - Move formation up")
        print("  down       - Move formation down")
        print("  status     - Show formation status")
        print("  quit       - Exit")
        print("="*60)
        
        # Command handlers
        commands = {
            'arm': lambda: formation.arm_all(),
            'takeoff': lambda: formation.takeoff_formation(),
            'land': lambda: formation.land_formation(),
            'start': lambda: formation.start_formation(),
            'stop': lambda: formation.stop_formation(),
            'line': lambda: formation.set_formation('line'),
            'triangle': lambda: formation.set_formation('triangle'),
            'square': lambda: formation.set_formation('square'),
            'circle': lambda: formation.set_formation('circle'),
            'diamond': lambda: formation.set_formation('diamond'),
            'forward': lambda: formation.move_formation(5, 0, 0),
            'backward': lambda: formation.move_formation(-5, 0, 0),
            'left': lambda: formation.move_formation(0, 5, 0),
            'right': lambda: formation.move_formation(0, -5, 0),
            'up': lambda: formation.move_formation(0, 0, 5),
            'down': lambda: formation.move_formation(0, 0, -5),
            'status': lambda: print(f"Status: {formation.get_status()}")
        }
        
        # Main control loop
        while True:
            try:
                command = input("\nFormation Command: ").strip().lower()
                
                if command == 'quit':
                    break
                elif command in commands:
                    commands[command]()
                else:
                    print("Unknown command")
                    
            except KeyboardInterrupt:
                break
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'formation' in locals():
            formation.stop_formation()
            formation.land_formation()
            formation.destroy_node()
        rclpy.shutdown()
        print("👋 Formation controller shutdown")


if __name__ == '__main__':
    main()
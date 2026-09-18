import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
import logging
from datetime import datetime, timedelta
from simulation.environment import EnvironmentModel
from simulation.systems.hvac import HVACModel
from simulation.systems.chp import PowerGrid
from simulation.systems.fuel import FuelModel
from simulation.systems.water import WaterModel
from simulation.systems.wastewater import WastewaterModel
from simulation.systems.communication import CommunicationModel
from simulation.systems.vehicle import VehicleFleet
from simulation.systems.inventory import InventoryModel
from simulation.systems.human import HumanAssetModel
from simulation.faults import FaultManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class SimulationEngine:
    def __init__(self, use_real_clock=True, time_acceleration=1):
        if use_real_clock:
            self.current_time = datetime.utcnow()
        else:
            self.current_time = datetime.fromisoformat("2026-08-29T12:00:00+00:00")
            
        self.time_acceleration = time_acceleration 
        self.last_sim_time = self.current_time
        
        self.state = {
            "station": "BHARATI",
            "timestamp": self.current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "environment": {}
        }
        
        self.fault_manager = FaultManager()
        self.environment_model = EnvironmentModel()
        self.hvac_model = HVACModel(self.fault_manager)
        self.power_model = PowerGrid(self.fault_manager)
        self.fuel_model = FuelModel(self.fault_manager)
        self.water_model = WaterModel(self.fault_manager)
        self.wastewater_model = WastewaterModel(self.fault_manager)
        self.communication_model = CommunicationModel(self.fault_manager)
        self.vehicle_model = VehicleFleet(self.fault_manager)
        self.inventory_model = InventoryModel(self.fault_manager)
        self.human_model = HumanAssetModel(self.fault_manager)
        
        # Order matters: Environment -> Human -> Vehicles -> HVAC -> Power -> Fuel -> Water -> Wastewater -> Communication -> Inventory
        self.models = [self.environment_model, self.human_model, self.vehicle_model, self.hvac_model, self.power_model, self.fuel_model, self.water_model, self.wastewater_model, self.communication_model, self.inventory_model]
        self.tick_count = 0

    def step(self):
        self.tick_count += 1
        
        # Advance clock
        self.current_time += timedelta(seconds=self.time_acceleration)
        self.state["timestamp"] = self.current_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # FIX: Calculate exact delta-time (dt) in seconds passed in simulation
        dt_seconds = int((self.current_time - self.last_sim_time).total_seconds())
        self.last_sim_time = self.current_time
        
        # AUTO-DISPATCH MTTR WORK ORDERS
        for fault_id in list(self.fault_manager.active_faults.keys()):
            if not any(r["fault_id"] == fault_id for r in self.inventory_model.active_repairs):
                self.inventory_model.dispatch_work_order(fault_id, self.state)
                logging.info(f"AUTO-DISPATCH: Mechanic deployed for {fault_id}")
        
        
        for model in self.models:
            # Pass sim_time AND dt to models for physically accurate thermal inertia
            if hasattr(model, 'update'):
                model.update(self.state, sim_time=self.current_time, dt=dt_seconds)
            
        self.state["faults"] = self.fault_manager.active_faults
        return self.state

    def run_realtime(self):
        logging.info("Starting Bharati Digital Twin Simulator...")
        try:
            while True:
                current_state = self.step()
                
                os.system('cls' if os.name == 'nt' else 'clear')
                print(f"--- BHARATI STATION LIVE TELEMETRY (Tick: {self.tick_count} | Speed: {self.time_acceleration}x) ---")
                print(f"Time: {self.state['timestamp']}")
                print(json.dumps(current_state, indent=2))
                
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("Simulator stopped.")

if __name__ == "__main__":
    # Back to 1x normal speed so you can see the ultra-smooth physics per second
    engine = SimulationEngine(use_real_clock=True, time_acceleration=1)
    engine.run_realtime()

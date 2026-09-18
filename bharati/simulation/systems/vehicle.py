import math
import random
import logging
from enum import Enum

class VehicleState(Enum):
    OFF_UNPLUGGED = 0
    OFF_PLUGGED_IN = 1
    CRANKING = 2
    RUNNING = 3
    FAULT_SHUTDOWN = 4

class VehicleType(Enum):
    PISTENBULLY = 1
    SNOWMOBILE = 2

class VehicleUnit:
    def __init__(self, unit_id: str, v_type: VehicleType, fault_manager):
        self.unit_id = unit_id
        self.type = v_type
        self.fault_manager = fault_manager
        
        self.state = VehicleState.OFF_PLUGGED_IN
        
        # Specs
        if self.type == VehicleType.PISTENBULLY:
            self.mass_kg = 10000.0
            self.engine_thermal_mass_kj_k = 500.0
            self.fuel_capacity_L = 250.0
            self.max_load_kw = 300.0
            self.block_heater_kw = 2.5
        else:
            self.mass_kg = 300.0
            self.engine_thermal_mass_kj_k = 50.0
            self.fuel_capacity_L = 40.0
            self.max_load_kw = 80.0
            self.block_heater_kw = 0.5
            
        # Physical State
        self.fuel_level_L = self.fuel_capacity_L
        self.engine_block_temp_c = 5.0
        self.battery_temp_c = 5.0
        self.battery_soc_pct = 100.0
        self.cabin_temp_c = 5.0
        
        # Derived/Dynamic
        self.oil_viscosity_cSt = 10.0
        self.fuel_viscosity_cSt = 2.0
        self.engine_load_kw = 0.0
        self.speed_kmh = 0.0
        self.rpm = 0.0
        
        self.register_faults()
        
    def register_faults(self):
        fm = self.fault_manager
        uid = self.unit_id
        fm.register_spof(f"{uid}_DIESEL_GELLING", "Fuel line heater fails, fuel gels")
        fm.register_spof(f"{uid}_BATTERY_FREEZE", "Battery blanket fails")
        fm.register_spof(f"{uid}_TRACK_DERAILMENT", "Instant loss of traction")
        fm.register_spof(f"{uid}_COOLANT_LEAK", "Overheating due to coolant loss")
        fm.register_spof(f"{uid}_ALTERNATOR_FAIL", "Battery drains while running")

    def get_cca_available(self):
        # Peukert-like exponential drop for Cold Cranking Amps
        # Assuming rated CCA is 1000. At -30C, it drops by ~70%.
        rated_cca = 1000.0 if self.type == VehicleType.PISTENBULLY else 300.0
        if self.battery_temp_c >= 20.0:
            temp_penalty = 1.0
        else:
            # Exponential decay below 20C
            # At -30C: (20 - -30) = 50. exp(-0.03 * 50) = 0.22 (22% CCA left)
            temp_penalty = math.exp(-0.03 * (20.0 - self.battery_temp_c))
            
        # SOC penalty
        soc_penalty = max(0.1, self.battery_soc_pct / 100.0)
        return rated_cca * temp_penalty * soc_penalty

    def calculate_viscosity(self, temp_c, is_fuel=False):
        if is_fuel:
            # Diesel/Jet-A gelling
            if temp_c <= -47.0: return 1000.0
            if temp_c > 15.0: return 2.0
            return 2.0 + math.exp(-0.1 * (temp_c + 20.0))
        else:
            # Engine Oil (Synthetic 0W-40)
            if temp_c <= -50.0: return 10000.0 # Solid
            if temp_c > 90.0: return 10.0 # Optimal
            return 10.0 + math.exp(-0.06 * (temp_c - 10.0))

    def update(self, dt: int, env: dict, has_grid_power: bool):
        if dt <= 0: dt = 1
        fm = self.fault_manager
        uid = self.unit_id
        
        amb_temp = env.get("ambient_temperature_c", -15.0)
        wind_chill = env.get("wind_chill_c", -25.0)
        wind_speed_ms = env.get("wind_speed_ms", 5.0)
        blizzard = (env.get("state") == "BLIZZARD")
        
        # Faults
        gelling = fm.is_fault_active(f"{uid}_DIESEL_GELLING")
        batt_freeze = fm.is_fault_active(f"{uid}_BATTERY_FREEZE")
        derailment = fm.is_fault_active(f"{uid}_TRACK_DERAILMENT")
        coolant_leak = fm.is_fault_active(f"{uid}_COOLANT_LEAK")
        alt_fail = fm.is_fault_active(f"{uid}_ALTERNATOR_FAIL")
        
        # 1. Block Heater & Thermodynamics (Exponential Decay / Newton's Law)
        heat_loss_coef = 0.5 if self.type == VehicleType.PISTENBULLY else 0.1
        
        heat_gen_kw = 0.0
        battery_heat_kw = 0.0
        
        # If parked and plugged in
        if self.state == VehicleState.OFF_PLUGGED_IN:
            if has_grid_power:
                heat_gen_kw = self.block_heater_kw
                battery_heat_kw = 0.2 if batt_freeze == 0 else 0.0 # Battery blanket
                # Trickle charge
                self.battery_soc_pct = min(100.0, self.battery_soc_pct + (1.0 * dt / 3600.0))
                
        elif self.state == VehicleState.RUNNING:
            heat_gen_kw = self.engine_load_kw * 1.5
            battery_heat_kw = 0.5 # Warmed by engine bay
            
        # Apply Thermal Physics (Exponential for stability at high dt)
        if coolant_leak > 0 and self.state == VehicleState.RUNNING:
            heat_loss_coef *= 5.0 # Loss of coolant means rapid heat exchange with air? No, it means loss of cooling... Wait, coolant leak means engine overheats if running, but cools faster if off. 
            
        # Engine Block Temp
        engine_cooling_rate = 0.001 if self.type == VehicleType.PISTENBULLY else 0.005
        target_engine_temp = wind_chill
        if heat_gen_kw > 0:
            target_engine_temp = wind_chill + (heat_gen_kw / heat_loss_coef)
            
        self.engine_block_temp_c = target_engine_temp + (self.engine_block_temp_c - target_engine_temp) * math.exp(-engine_cooling_rate * dt)
        
        # Battery Temp 
        batt_cooling_rate = 0.005
        target_batt_temp = wind_chill
        if battery_heat_kw > 0:
            target_batt_temp = wind_chill + (battery_heat_kw / 0.05)
            
        self.battery_temp_c = target_batt_temp + (self.battery_temp_c - target_batt_temp) * math.exp(-batt_cooling_rate * dt)
        
        # 2. Fluid Viscosity
        self.oil_viscosity_cSt = self.calculate_viscosity(self.engine_block_temp_c, is_fuel=False)
        fuel_temp = wind_chill if (gelling > 0 or self.state != VehicleState.RUNNING) else self.engine_block_temp_c
        self.fuel_viscosity_cSt = self.calculate_viscosity(fuel_temp, is_fuel=True)
        
        # 3. State Machine & Mechanical Physics
        if self.state in [VehicleState.OFF_PLUGGED_IN, VehicleState.OFF_UNPLUGGED]:
            self.rpm = 0.0
            self.speed_kmh = 0.0
            self.engine_load_kw = 0.0
            
            # Cabin cools down exponentially
            cabin_cooling_rate = 0.003
            self.cabin_temp_c = wind_chill + (self.cabin_temp_c - wind_chill) * math.exp(-cabin_cooling_rate * dt)
            
            # Simulate a user trying to start it (Random event for simulation)
            if random.random() < (0.005 * dt) and self.fuel_level_L > 5.0:
                self.state = VehicleState.CRANKING
                
        elif self.state == VehicleState.CRANKING:
            # Cranking physics
            cca_req = 400.0 if self.type == VehicleType.PISTENBULLY else 150.0
            # Higher viscosity = harder to crank
            viscosity_drag = min(2.0, self.oil_viscosity_cSt / 100.0)
            cca_req *= (1.0 + viscosity_drag)
            
            self.battery_soc_pct = max(0.0, self.battery_soc_pct - (0.5 * dt)) # Cranking drains battery
            
            if self.get_cca_available() >= cca_req and self.fuel_viscosity_cSt < 1000.0:
                self.state = VehicleState.RUNNING
            else:
                # Failed to start
                if random.random() < 0.1: # Give up after some time
                    self.state = VehicleState.OFF_UNPLUGGED
                    logging.warning(f"{uid} failed to crank! CCA Available: {self.get_cca_available():.1f} vs Req: {cca_req:.1f}")
                    
        elif self.state == VehicleState.RUNNING:
            # RPM & Speed (Random drive cycle)
            target_speed = 15.0 if self.type == VehicleType.PISTENBULLY else 40.0
            if blizzard: target_speed *= 0.5 # Slow down
            if derailment > 0: target_speed = 0.0
            
            self.speed_kmh = (0.9 * self.speed_kmh) + (0.1 * target_speed)
            self.rpm = 1000.0 + (self.speed_kmh * 20.0)
            
            # Load Physics (Aero drag + rolling resistance)
            # Drag increases square of wind relative speed
            relative_wind_kmh = (wind_speed_ms * 3.6) + self.speed_kmh
            aero_drag_kw = 0.001 * (relative_wind_kmh ** 2)
            rolling_res_kw = (self.mass_kg * 9.81 * 0.2 * (self.speed_kmh / 3.6)) / 1000.0
            viscosity_drag_kw = self.oil_viscosity_cSt * 0.1
            
            self.engine_load_kw = aero_drag_kw + rolling_res_kw + viscosity_drag_kw
            
            # Fuel Consumption (BSFC approx 0.3 L/kWh)
            fuel_burn = (self.engine_load_kw * 0.3 * dt) / 3600.0
            self.fuel_level_L = max(0.0, self.fuel_level_L - fuel_burn)
            
            # Alternator
            if alt_fail == 0:
                self.battery_soc_pct = min(100.0, self.battery_soc_pct + (2.0 * dt / 3600.0))
            else:
                self.battery_soc_pct = max(0.0, self.battery_soc_pct - (5.0 * dt / 3600.0))
                
            # Cabin Heating
            cabin_cooling_rate = 0.003
            target_cabin = wind_chill
            if self.engine_block_temp_c > 40.0:
                target_cabin = 20.0
            self.cabin_temp_c = target_cabin + (self.cabin_temp_c - target_cabin) * math.exp(-cabin_cooling_rate * dt)
                
            # Fault Checks
            if self.battery_soc_pct <= 0.0 or self.fuel_level_L <= 0.0 or self.fuel_viscosity_cSt >= 1000.0:
                self.state = VehicleState.FAULT_SHUTDOWN
                logging.critical(f"{uid} STALLED OUT ON THE ICE!")
            if self.engine_block_temp_c > 115.0:
                self.state = VehicleState.FAULT_SHUTDOWN
                logging.critical(f"{uid} THERMAL MELTDOWN!")
                
            # Randomly park
            if random.random() < (0.002 * dt):
                self.state = VehicleState.OFF_PLUGGED_IN if has_grid_power else VehicleState.OFF_UNPLUGGED
                
        elif self.state == VehicleState.FAULT_SHUTDOWN:
            self.rpm = 0.0
            self.speed_kmh = 0.0
            self.engine_load_kw = 0.0
            cabin_cooling_rate = 0.003
            self.cabin_temp_c = wind_chill + (self.cabin_temp_c - wind_chill) * math.exp(-cabin_cooling_rate * dt)
            # Auto-recover if faults cleared (Simulating mechanic fixing it)
            if self.battery_soc_pct > 10.0 and self.fuel_level_L > 0.0 and self.engine_block_temp_c < 100.0:
                if alt_fail == 0 and coolant_leak == 0 and gelling == 0:
                    if random.random() < 0.01:
                        self.state = VehicleState.OFF_PLUGGED_IN

class VehicleFleet:
    def __init__(self, fault_manager):
        self.vehicles = [
            VehicleUnit("PB-1", VehicleType.PISTENBULLY, fault_manager),
            VehicleUnit("PB-2", VehicleType.PISTENBULLY, fault_manager),
            VehicleUnit("SM-1", VehicleType.SNOWMOBILE, fault_manager),
            VehicleUnit("SM-2", VehicleType.SNOWMOBILE, fault_manager)
        ]
        self.total_block_heater_kw = 0.0
        
    def update(self, state: dict, sim_time=None, dt: int = 1):
        if dt <= 0: dt = 1
        
        env = state.get("environment", {})
        grid_status = state.get("power", {}).get("grid_status", "ONLINE")
        has_grid_power = (grid_status == "ONLINE")
        
        self.total_block_heater_kw = 0.0
        fuel_requested_L = 0.0
        
        v_data = {}
        for v in self.vehicles:
            v.update(dt, env, has_grid_power)
            
            # Grid Load calculation
            if v.state == VehicleState.OFF_PLUGGED_IN and has_grid_power:
                self.total_block_heater_kw += v.block_heater_kw
                
            # Refueling Logic (If parked and fuel < 50%)
            if v.state in [VehicleState.OFF_PLUGGED_IN, VehicleState.OFF_UNPLUGGED] and v.fuel_level_L < (v.fuel_capacity_L * 0.5):
                refuel_amount = (5.0 * dt) # 5 L/s pump
                space_available = v.fuel_capacity_L - v.fuel_level_L
                actual_refuel = min(refuel_amount, space_available)
                fuel_requested_L += actual_refuel
                v.fuel_level_L += actual_refuel
                
            v_data[v.unit_id] = {
                "state": v.state.name,
                "speed_kmh": round(v.speed_kmh, 1),
                "engine_load_kw": round(v.engine_load_kw, 1),
                "fuel_level_L": round(v.fuel_level_L, 1),
                "engine_block_temp_c": round(v.engine_block_temp_c, 1),
                "battery_temp_c": round(v.battery_temp_c, 1),
                "battery_soc_pct": round(v.battery_soc_pct, 1),
                "cca_available": int(v.get_cca_available()),
                "oil_viscosity_cSt": round(v.oil_viscosity_cSt, 1),
                "fuel_viscosity_cSt": round(v.fuel_viscosity_cSt, 1),
                "cabin_temp_c": round(v.cabin_temp_c, 1)
            }
            
        state["vehicles"] = {
            "fleet": v_data,
            "total_block_heater_kw": round(self.total_block_heater_kw, 1),
            "fuel_requested_L": round(fuel_requested_L, 2)
        }
        
        return state

import logging
import math
import random

class CentrifugalSeparator:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        self.rpm = 0.0
        self.water_extracted_liters = 0.0
        self.is_running = False

    def update(self, flow_rate_L_s, dt):
        motor_fail = self.fault_manager.is_fault_active("FUEL_SEPARATOR_MOTOR_FAIL")
        dump_fail = self.fault_manager.is_fault_active("FUEL_SEPARATOR_WATER_DUMP_FAIL")
        
        if self.is_running and not motor_fail:
            self.rpm = min(10000.0, self.rpm + (1000.0 * dt))
        else:
            self.rpm = max(0.0, self.rpm - (500.0 * dt))
            
        water_passed_to_day_tank = 0.0
        
        # If fuel is flowing but separator isn't spinning, water goes straight through!
        if flow_rate_L_s > 0:
            inherent_water = flow_rate_L_s * 0.001 * dt # 0.1% water condensation
            
            if self.rpm > 8000:
                if dump_fail > 0:
                    # Extracts water but can't dump it. Overflows into clean line.
                    water_passed_to_day_tank = inherent_water
                else:
                    self.water_extracted_liters += inherent_water
            else:
                water_passed_to_day_tank = inherent_water
                
        return water_passed_to_day_tank


class FuelModel:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        
        # Storage
        self.main_farm_level_L = 200000.0
        self.main_farm_capacity_L = 200000.0
        self.day_tank_level_L = 2000.0
        self.day_tank_capacity_L = 2000.0
        self.water_in_day_tank_L = 0.0
        
        # Physics (Jet A-1 SAB)
        self.fuel_temp_c = -15.0 # Outdoor pipe temp
        self.viscosity_cSt = 2.0
        self.heat_trace_active = True
        
        # Pumping (Duplex)
        self.pump_a_active = False
        self.pump_b_active = False
        self.flow_rate_L_s = 0.0
        
        self.separator = CentrifugalSeparator(fault_manager)
        self.electrical_demand_kw = 0.0
        
        self.register_faults()
        
    def register_faults(self):
        fm = self.fault_manager
        fm.register_spof("FUEL_MAIN_FARM_LEAK", "Outdoor tank rupture")
        fm.register_spof("FUEL_HEAT_TRACE_FAIL", "Piping heat trace dies, fuel gels below -47C")
        fm.register_spof("FUEL_DAY_TANK_LEAK", "Indoor day tank rupture")
        fm.register_spof("FUEL_PUMP_A_FAIL", "Primary transfer pump fail")
        fm.register_spof("FUEL_PUMP_B_FAIL", "Standby transfer pump fail")
        fm.register_spof("FUEL_SEPARATOR_MOTOR_FAIL", "Centrifuge stops spinning")
        fm.register_spof("FUEL_SEPARATOR_WATER_DUMP_FAIL", "Centrifuge cannot dump extracted sludge")

    def calculate_viscosity(self, temp_c):
        # Jet A-1 is fluid down to -47C. 
        # Exponential viscosity spike near freezing point.
        if temp_c <= -47.0:
            return 1000.0 # Solid gel / Blocked
        # Base viscosity is low (2.0 cSt at 15C). Increases as it gets colder.
        # Simple curve: 2.0 at 15C, 8.0 at -20C, 50.0 at -40C, 1000 at -47C
        if temp_c > 15: return 2.0
        return 2.0 + math.exp(-0.1 * (temp_c + 20.0))

    def update(self, state: dict, sim_time=None, dt: int = 1):
        if dt <= 0: dt = 1
        
        env = state.get("environment", {})
        amb_temp = env.get("ambient_temperature_c", -15.0)
        
        fm = self.fault_manager
        main_leak = fm.is_fault_active("FUEL_MAIN_FARM_LEAK")
        day_leak = fm.is_fault_active("FUEL_DAY_TANK_LEAK")
        ht_fail = fm.is_fault_active("FUEL_HEAT_TRACE_FAIL")
        pump_a_fail = fm.is_fault_active("FUEL_PUMP_A_FAIL")
        pump_b_fail = fm.is_fault_active("FUEL_PUMP_B_FAIL")
        
        self.electrical_demand_kw = 0.0
        
        # 0. Power Grid Check
        grid_status = state.get("power", {}).get("grid_status", "ONLINE")
        has_power = (grid_status == "ONLINE")
        
        # 1. Thermal & Viscosity Physics (Pipe Thermal Mass)
        target_temp = amb_temp
        self.electrical_demand_kw = 0.0
        
        if ht_fail == 0 and self.fuel_temp_c < -15.0 and has_power:
            self.heat_trace_active = True
            target_temp = 5.0 # Heater tries to keep it warm
            self.electrical_demand_kw += 15.0 # Heating load
        else:
            self.heat_trace_active = False
            target_temp = amb_temp
            
        # Newton's law of cooling for the pipe (slow temp change)
        temp_diff = target_temp - self.fuel_temp_c
        # Pipe thermal mass means it takes ~2 hours to equalize
        cooling_rate = (temp_diff * dt) / 7200.0 
        self.fuel_temp_c += cooling_rate
            
        self.viscosity_cSt = self.calculate_viscosity(self.fuel_temp_c)
        
        # 2. Logistics (CHP Consumption)
        chp_consumption_L_hr = state.get("power", {}).get("total_fuel_consumption_L_hr", 0.0)
        consumption_L_s = chp_consumption_L_hr / 3600.0
        
        # Mass balance: Consuming fuel also consumes the water mixed in it
        water_ratio = self.water_in_day_tank_L / self.day_tank_level_L if self.day_tank_level_L > 0 else 0
        water_consumed_L = consumption_L_s * dt * water_ratio
        
        # Vehicle refueling pulls directly from the day tank
        vehicle_refuel_L = state.get("vehicles", {}).get("fuel_requested_L", 0.0)
        
        self.day_tank_level_L = max(0.0, self.day_tank_level_L - (consumption_L_s * dt) - vehicle_refuel_L)
        self.water_in_day_tank_L = max(0.0, self.water_in_day_tank_L - water_consumed_L - (vehicle_refuel_L * water_ratio))
        
        # 3. Leaks
        if main_leak > 0: self.main_farm_level_L -= (5.0 * dt) # 5 L/s massive leak
        if day_leak > 0: self.day_tank_level_L -= (0.5 * dt)
        self.main_farm_level_L = max(0.0, self.main_farm_level_L)
        self.day_tank_level_L = max(0.0, self.day_tank_level_L)
        
        # 4. Pumping Logic (Duty/Standby auto-failover)
        self.flow_rate_L_s = 0.0
        pump_flow_capacity = 2.0 # L/s
        
        if self.day_tank_level_L < (self.day_tank_capacity_L * 0.8) and self.main_farm_level_L > 0 and has_power:
            # Need to refill
            if pump_a_fail == 0:
                self.pump_a_active = True
                self.pump_b_active = False
            elif pump_b_fail == 0:
                # Auto fail-over to standby!
                self.pump_a_active = False
                self.pump_b_active = True
            else:
                self.pump_a_active = False
                self.pump_b_active = False
                
            # Calculate actual flow based on viscosity
            if self.pump_a_active or self.pump_b_active:
                self.electrical_demand_kw += 5.0 # Pump power
                self.separator.is_running = True
                self.electrical_demand_kw += 2.0 # Separator motor
                
                # Flow drops if viscosity is high. Solidifies at 1000 cSt.
                if self.viscosity_cSt >= 1000.0:
                    self.flow_rate_L_s = 0.0
                else:
                    self.flow_rate_L_s = pump_flow_capacity * (2.0 / self.viscosity_cSt)
                    self.flow_rate_L_s = min(pump_flow_capacity, self.flow_rate_L_s)
                    
                # Transfer fuel
                transfer_amt = self.flow_rate_L_s * dt
                transfer_amt = min(transfer_amt, self.day_tank_capacity_L - self.day_tank_level_L)
                transfer_amt = min(transfer_amt, self.main_farm_level_L)
                
                self.main_farm_level_L -= transfer_amt
                self.day_tank_level_L += transfer_amt
        else:
            self.pump_a_active = False
            self.pump_b_active = False
            self.separator.is_running = False
            
        # 5. Separator & Contamination Physics
        water_bypassed = self.separator.update(self.flow_rate_L_s, dt)
        self.water_in_day_tank_L += water_bypassed
        
        # Calculate water concentration (ppm)
        water_ppm = 0.0
        if self.day_tank_level_L > 0:
            water_ppm = (self.water_in_day_tank_L / self.day_tank_level_L) * 1000000.0
            
        # 6. Global State Update
        autonomy_days = 0.0
        if chp_consumption_L_hr > 0:
            autonomy_days = self.main_farm_level_L / (chp_consumption_L_hr * 24)
            
        state["fuel"] = {
            "main_farm_level_L": round(self.main_farm_level_L, 1),
            "day_tank_level_L": round(self.day_tank_level_L, 1),
            "autonomy_days": round(autonomy_days, 1),
            "fuel_temp_c": round(self.fuel_temp_c, 1),
            "viscosity_cSt": round(self.viscosity_cSt, 2),
            "pumps": {
                "pump_a_active": self.pump_a_active,
                "pump_b_active": self.pump_b_active,
                "flow_rate_L_s": round(self.flow_rate_L_s, 2)
            },
            "separator": {
                "rpm": int(self.separator.rpm),
                "water_extracted_L": round(self.separator.water_extracted_liters, 2),
                "water_in_day_tank_ppm": int(water_ppm)
            },
            "electrical_demand_kw": round(self.electrical_demand_kw, 1)
        }
        return state

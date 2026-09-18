import math
import random
import logging
from enum import Enum

class CHPState(Enum):
    OFF = 0
    CRANKING = 1
    WARM_UP = 2
    SYNCING = 3
    RUNNING = 4
    COOLDOWN = 5
    FAULT_SHUTDOWN = 6

class CHPUnit:
    def __init__(self, unit_id: str, capacity_kva: float, fault_manager):
        self.unit_id = unit_id
        self.capacity_kva = capacity_kva
        self.max_kw = capacity_kva * 0.8  
        
        self.state = CHPState.OFF
        self.timer = 0
        self.operating_hours = 0.0
        
        # --- Physics Variables ---
        self.rpm = 0.0
        self.current_load_kw = 0.0
        
        # Fuel System
        self.fuel_flow_L_hr = 0.0
        self.fuel_rail_pressure_bar = 0.0
        self.bsfc = 0.25 
        
        # Air & Exhaust (Turbocharger)
        self.boost_pressure_bar = 1.0
        self.air_to_fuel_ratio = 20.0
        self.exhaust_gas_temp_c = 20.0
        
        # Cooling System
        self.coolant_temp_c = 15.0 
        self.thermostat_open_pct = 0.0
        self.thermal_output_kw = 0.0
        
        # Lubrication
        self.oil_pressure_bar = 0.0
        self.oil_viscosity_pct = 100.0
        
        # Alternator
        self.voltage = 0.0
        self.frequency = 0.0
        self.stator_temp_c = 20.0
        self.vibration_mms = 0.0
        
        self.fault_manager = fault_manager
        self.register_faults()
        
    def register_faults(self):
        fm = self.fault_manager
        uid = self.unit_id
        # Fuel
        fm.register_spof(f"{uid}_INJECTOR_FOULING", "Gradual injector fouling")
        fm.register_spof(f"{uid}_FUEL_PUMP_WEAR", "Gradual loss of rail pressure")
        fm.register_spof(f"{uid}_WATER_IN_FUEL", "Transient bad combustion")
        # Air
        fm.register_spof(f"{uid}_AIR_FILTER_CLOG", "Gradual restriction of intake air")
        fm.register_spof(f"{uid}_TURBO_BEARING_FAIL", "Hard failure of turbo boost")
        fm.register_spof(f"{uid}_EXHAUST_RESTRICTION", "Gradual backpressure buildup")
        # Cooling
        fm.register_spof(f"{uid}_COOLANT_LEAK", "Catastrophic loss of coolant")
        fm.register_spof(f"{uid}_THERMOSTAT_STUCK_CLOSED", "Overheating, zero station heat")
        fm.register_spof(f"{uid}_THERMOSTAT_STUCK_OPEN", "Engine overcooling (wet stacking)")
        fm.register_spof(f"{uid}_HEAT_EXCHANGER_FOULING", "Loss of thermal transfer efficiency")
        # Lube
        fm.register_spof(f"{uid}_OIL_LEAK", "Catastrophic loss of oil pressure")
        fm.register_spof(f"{uid}_OIL_DEGRADATION", "Loss of oil viscosity")
        # Electrical
        fm.register_spof(f"{uid}_AVR_FAILURE", "Wild voltage swings")
        fm.register_spof(f"{uid}_BEARING_WEAR", "High alternator vibration")

    def _apply_faults_and_physics(self, dt: int, glycol_return_temp_c: float = 15.0):
        load_pct = self.current_load_kw / self.max_kw
        fm = self.fault_manager
        uid = self.unit_id
        
        # 1. FUEL SYSTEM PHYSICS
        fuel_pump_wear = fm.is_fault_active(f"{uid}_FUEL_PUMP_WEAR")
        injector_foul = fm.is_fault_active(f"{uid}_INJECTOR_FOULING")
        water_in_fuel = fm.is_fault_active(f"{uid}_WATER_IN_FUEL")
        
        self.fuel_rail_pressure_bar = 1200.0 * (1.0 - (fuel_pump_wear * 0.4)) + random.gauss(0, 5)
        
        # Base BSFC Curve
        if load_pct < 0.2: self.bsfc = 0.45
        elif load_pct < 0.5: self.bsfc = 0.35
        elif load_pct < 0.8: self.bsfc = 0.28
        else: self.bsfc = 0.25
        
        # Inefficient combustion penalties
        self.bsfc *= (1.0 + (injector_foul * 0.25))
        if water_in_fuel > 0:
            self.bsfc *= (1.0 + (random.random() * 0.2)) # Erratic
            
        self.fuel_flow_L_hr = self.current_load_kw * self.bsfc
        
        # 2. AIR & EXHAUST (TURBO) PHYSICS
        filter_clog = fm.is_fault_active(f"{uid}_AIR_FILTER_CLOG")
        turbo_fail = fm.is_fault_active(f"{uid}_TURBO_BEARING_FAIL")
        exhaust_restr = fm.is_fault_active(f"{uid}_EXHAUST_RESTRICTION")
        
        target_boost = 1.0 + (1.5 * load_pct)
        if turbo_fail > 0: target_boost = 1.0 # Naturally aspirated
        self.boost_pressure_bar = target_boost * (1.0 - (filter_clog * 0.4))
        
        # Air to Fuel Ratio (Rich vs Lean)
        # Normal is 20.0. Drops if fuel flow is high but air is restricted.
        self.air_to_fuel_ratio = 20.0 * (self.boost_pressure_bar / target_boost) 
        self.air_to_fuel_ratio /= (1.0 + injector_foul)
        
        # Exhaust Gas Temp (EGT)
        # Normal 350-500. Drops if rich? Actually Diesel EGT spikes heavily when running rich (unburned fuel burning in exhaust)
        base_egt = 300.0 + (250.0 * load_pct)
        # Rich mixture penalty
        afr_penalty = max(0, 18.0 - self.air_to_fuel_ratio) * 40.0 
        self.exhaust_gas_temp_c = base_egt + afr_penalty + (exhaust_restr * 150.0) + random.gauss(0, 2)
        
        # 3. COOLING & THERMAL RECOVERY PHYSICS
        heat_generated_kw = self.current_load_kw * 1.5 * (self.bsfc / 0.25) # More fuel = more waste heat
        
        coolant_leak = fm.is_fault_active(f"{uid}_COOLANT_LEAK")
        therm_closed = fm.is_fault_active(f"{uid}_THERMOSTAT_STUCK_CLOSED")
        therm_open = fm.is_fault_active(f"{uid}_THERMOSTAT_STUCK_OPEN")
        hx_fouling = fm.is_fault_active(f"{uid}_HEAT_EXCHANGER_FOULING")
        
        # Thermostat logic
        if therm_closed > 0:
            target_therm = 0.0
        elif therm_open > 0:
            target_therm = 100.0
        else:
            if self.coolant_temp_c < 82.0: target_therm = 0.0
            elif self.coolant_temp_c > 90.0: target_therm = 100.0
            else: target_therm = ((self.coolant_temp_c - 82.0) / 8.0) * 100.0
            
        self.thermostat_open_pct = (0.1 * target_therm) + (0.9 * self.thermostat_open_pct)
        
        # Heat transfer to station
        hx_efficiency = 0.9 * (1.0 - (hx_fouling * 0.6))
        self.thermal_output_kw = heat_generated_kw * (self.thermostat_open_pct / 100.0) * hx_efficiency
        
        # Internal block temperature dynamics
        fluid_loss = coolant_leak * 0.99 # Nearly 100% loss of cooling ability
        
        # If return temp from station is very hot (e.g. 70C+), we can't shed as much heat!
        # Base cooling assumes return water is 40C.
        temp_delta_penalty = max(0, glycol_return_temp_c - 40.0) / 40.0
        cooling_capacity = self.thermal_output_kw * (1.0 - temp_delta_penalty) + (heat_generated_kw * 0.1)
        cooling_capacity *= (1.0 - fluid_loss)
        
        temp_change = ((heat_generated_kw - cooling_capacity) * dt) / 300.0 # Thermal mass
        self.coolant_temp_c += temp_change
        
        # 4. LUBRICATION PHYSICS
        oil_leak = fm.is_fault_active(f"{uid}_OIL_LEAK")
        oil_deg = fm.is_fault_active(f"{uid}_OIL_DEGRADATION")
        
        self.oil_viscosity_pct = 100.0 - (oil_deg * 40.0) - (self.coolant_temp_c - 90.0 if self.coolant_temp_c > 90 else 0) * 0.5
        base_oil_pressure = 4.5 + (0.5 * load_pct)
        viscosity_drop = (100.0 - self.oil_viscosity_pct) * 0.02
        self.oil_pressure_bar = base_oil_pressure - viscosity_drop - (oil_leak * 4.0) + random.gauss(0, 0.05)
        
        # 5. ELECTRICAL & ALTERNATOR PHYSICS
        avr_fail = fm.is_fault_active(f"{uid}_AVR_FAILURE")
        bearing_wear = fm.is_fault_active(f"{uid}_BEARING_WEAR")
        
        # Voltage
        target_voltage = 400.0
        if avr_fail > 0:
            target_voltage += math.sin(self.operating_hours * 100) * 40.0 * avr_fail
        self.voltage = target_voltage + random.gauss(0, 0.5)
        
        # Vibration
        base_vib = 1.0 + (1.5 * load_pct)
        # Misfires (injector foul / water) cause harsh vibration
        misfire_vib = (injector_foul * 5.0) + (water_in_fuel * 8.0)
        self.vibration_mms = base_vib + misfire_vib + (bearing_wear * 12.0) + random.gauss(0, 0.2)
        
        # Stator Temp
        self.stator_temp_c = 40.0 + (load_pct * 60.0) + (bearing_wear * 30.0) + random.gauss(0, 0.5)
        
        # Safety Shutdowns
        if self.coolant_temp_c > 105.0 or self.oil_pressure_bar < 1.0 or self.exhaust_gas_temp_c > 750.0:
            logging.critical(f"{uid} EMERGENCY SHUTDOWN! Temp: {self.coolant_temp_c:.1f}, Oil: {self.oil_pressure_bar:.1f}, EGT: {self.exhaust_gas_temp_c:.0f}")
            self.state = CHPState.FAULT_SHUTDOWN
            self.current_load_kw = 0.0
            self.thermal_output_kw = 0.0

    def update(self, dt: int, glycol_return_temp_c: float = 15.0, has_fuel: bool = True, water_contamination: bool = False):
        if not has_fuel and self.state in [CHPState.RUNNING, CHPState.SYNCING, CHPState.WARM_UP, CHPState.CRANKING]:
            logging.critical(f"{self.unit_id} EMERGENCY SHUTDOWN! Out of fuel!")
            self.state = CHPState.FAULT_SHUTDOWN
            self.current_load_kw = 0.0
            self.thermal_output_kw = 0.0
            
        if water_contamination:
            # Overwrite FaultManager if physically contaminated by separator
            self.fault_manager.active_faults[f"{self.unit_id}_WATER_IN_FUEL"] = 1.0
            
        if self.state == CHPState.OFF:
            self.rpm = 0.0
            self.oil_pressure_bar = 0.0
            self.coolant_temp_c = max(15.0, self.coolant_temp_c - (0.01 * dt))
            return
            
        elif self.state == CHPState.CRANKING:
            self.timer -= dt
            self.rpm = 300.0
            self.oil_pressure_bar = 1.5
            if self.timer <= 0:
                self.state = CHPState.WARM_UP
                self.timer = 15
                
        elif self.state == CHPState.WARM_UP:
            self.timer -= dt
            self.rpm = 1500.0
            self.oil_pressure_bar = 4.5
            self.coolant_temp_c += (0.5 * dt)
            if self.timer <= 0:
                self.state = CHPState.SYNCING
                self.timer = 5
                
        elif self.state == CHPState.SYNCING:
            self.timer -= dt
            self.rpm = 1500.0 + random.uniform(-2, 2)
            self.voltage = 400.0
            self.frequency = 50.0
            if self.timer <= 0:
                self.state = CHPState.RUNNING

        elif self.state == CHPState.RUNNING:
            self.operating_hours += (dt / 3600.0)
            
            # Droop Control
            load_pct = self.current_load_kw / self.max_kw
            self.rpm = 1500.0 - (15.0 * load_pct) + random.gauss(0, 0.5)
            self.frequency = self.rpm / 30.0 
            
            self._apply_faults_and_physics(dt, glycol_return_temp_c)
                
        elif self.state == CHPState.COOLDOWN:
            self.current_load_kw = 0.0
            self.rpm = 1500.0
            self._apply_faults_and_physics(dt, glycol_return_temp_c)
            self.timer -= dt
            if self.timer <= 0:
                self.state = CHPState.OFF


class PowerGrid:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        self.chps = [
            CHPUnit("CHP-1", 100, fault_manager),
            CHPUnit("CHP-2", 100, fault_manager),
            CHPUnit("CHP-3", 100, fault_manager)
        ]
        self.grid_voltage = 0.0
        self.grid_frequency = 0.0
        self.total_load_kw = 0.0
        self.total_thermal_kw = 0.0
        self.total_fuel_L_hr = 0.0
        self.fault_manager.register_spof("GRID_VOLTAGE_SAG", "Transient voltage sag on the main grid")
        
    def start_unit(self, unit_index):
        unit = self.chps[unit_index]
        if unit.state == CHPState.OFF:
            unit.state = CHPState.CRANKING
            unit.timer = 5
            
    def update(self, state: dict, sim_time, dt: int):
        hvac_state = state.get("hvac", {})
        hvac_elec_kw = hvac_state.get("total_electrical_demand_kw", 0.0)
        glycol_return_temp_c = hvac_state.get("glycol_return_temp_c", 15.0)
        
        fuel_elec_kw = state.get("fuel", {}).get("electrical_demand_kw", 0.0)
        water_elec_kw = state.get("water", {}).get("electrical_demand_kw", 0.0)
        wastewater_elec_kw = state.get("wastewater", {}).get("electrical_demand_kw", 0.0)
        vehicle_elec_kw = state.get("vehicles", {}).get("total_block_heater_kw", 0.0)
        
        base_station_kw = 25.0 
        self.total_load_kw = hvac_elec_kw + fuel_elec_kw + water_elec_kw + wastewater_elec_kw + vehicle_elec_kw + base_station_kw
        
        running_units = [u for u in self.chps if u.state == CHPState.RUNNING]
        available_capacity = sum([u.max_kw for u in running_units])
        
        if self.total_load_kw > (available_capacity * 0.85):
            for u in self.chps:
                if u.state == CHPState.OFF:
                    self.start_unit(self.chps.index(u))
                    break
        elif self.total_load_kw < ((available_capacity - 80) * 0.7) and len(running_units) > 1:
            running_units[-1].state = CHPState.COOLDOWN
            running_units[-1].timer = 60
            
        if len(running_units) == 0 and all(u.state == CHPState.OFF for u in self.chps) and all(u.state != CHPState.FAULT_SHUTDOWN for u in self.chps):
            self.start_unit(0)
            
        running_units = [u for u in self.chps if u.state == CHPState.RUNNING]
        if running_units:
            load_per_unit = self.total_load_kw / len(running_units)
            for u in running_units:
                u.current_load_kw = load_per_unit
        else:
            self.grid_voltage = 0.0
            self.grid_frequency = 0.0
            
        self.total_thermal_kw = 0.0
        self.total_fuel_L_hr = 0.0
        
        fuel_state = state.get("fuel", {})
        has_fuel = fuel_state.get("day_tank_level_L", 2000.0) > 0
        water_contamination = fuel_state.get("separator", {}).get("water_in_day_tank_ppm", 0) > 50
        
        for u in self.chps:
            u.update(dt, glycol_return_temp_c, has_fuel, water_contamination)
            
            # Immediate overload trip if load is > 110% of max capacity
            if u.state == CHPState.RUNNING and u.current_load_kw > (u.max_kw * 1.1):
                logging.critical(f"{u.unit_id} EMERGENCY SHUTDOWN! Overcurrent Trip (Load: {u.current_load_kw:.1f}kW > {u.max_kw*1.1:.1f}kW)")
                u.state = CHPState.FAULT_SHUTDOWN
                u.current_load_kw = 0.0
                
            self.total_thermal_kw += u.thermal_output_kw
            self.total_fuel_L_hr += u.fuel_flow_L_hr
            
        if running_units:
            self.grid_voltage = sum(u.voltage for u in running_units) / len(running_units)
            self.grid_frequency = sum(u.frequency for u in running_units) / len(running_units)
            sag = self.fault_manager.is_fault_active("GRID_VOLTAGE_SAG")
            if sag > 0:
                self.grid_voltage *= (1.0 - sag)
                
        chp_data = {}
        for u in self.chps:
            chp_data[u.unit_id] = {
                "state": u.state.name,
                "load_kw": round(u.current_load_kw, 1),
                "rpm": int(u.rpm),
                "voltage": round(u.voltage, 1),
                "oil_pressure_bar": round(u.oil_pressure_bar, 2),
                "oil_viscosity_pct": round(u.oil_viscosity_pct, 1),
                "coolant_temp_c": round(u.coolant_temp_c, 1),
                "thermostat_open_pct": round(u.thermostat_open_pct, 1),
                "fuel_flow_L_hr": round(u.fuel_flow_L_hr, 1),
                "fuel_rail_pressure_bar": int(self.chps[0].fuel_rail_pressure_bar),
                "boost_pressure_bar": round(u.boost_pressure_bar, 2),
                "air_to_fuel_ratio": round(u.air_to_fuel_ratio, 1),
                "exhaust_gas_temp_c": int(u.exhaust_gas_temp_c),
                "stator_temp_c": int(u.stator_temp_c),
                "vibration_mms": round(u.vibration_mms, 2),
                "thermal_output_kw": round(u.thermal_output_kw, 1),
                "operating_hours": round(u.operating_hours, 2)
            }
            
        grid_status = "ONLINE"
        if len(running_units) == 0 or self.grid_voltage < 320.0 or self.grid_frequency < 45.0:
            grid_status = "BLACKOUT"
            
        state["power"] = {
            "grid_status": grid_status,
            "grid_voltage": round(self.grid_voltage, 1),
            "grid_frequency": round(self.grid_frequency, 2),
            "total_load_kw": round(self.total_load_kw, 1),
            "total_thermal_supplied_kw": round(self.total_thermal_kw, 1),
            "total_fuel_consumption_L_hr": round(self.total_fuel_L_hr, 1),
            "generators": chp_data
        }
        return state

import logging
import math
import random

class AHU:
    def __init__(self, zone_name, fault_manager):
        self.zone_name = zone_name
        self.fault_manager = fault_manager
        self.fan_rpm = 0.0
        self.filter_health_pct = 100.0
        self.damper_open_pct = 0.0
        
        self.supply_air_temp_c = 0.0
        self.return_air_temp_c = 0.0

class Zone:
    def __init__(self, name, target_temp, volume_m3, insulation_u_value, surface_area, thermal_mass, fault_manager):
        self.name = name
        self.target_temp = target_temp
        self.current_temp = target_temp
        self.volume_m3 = volume_m3
        self.U = insulation_u_value
        self.A = surface_area
        self.thermal_mass = thermal_mass
        self.fault_manager = fault_manager
        
        self.ahu = AHU(name, fault_manager)
        self.co2_ppm = 400.0 if name == "LIVING" else None
        
        self.heat_demand_kw = 0.0
        self.glycol_mass_flow_kg_s = 0.0
        self.glycol_valve_open_pct = 0.0
        
    def calculate_losses_gains(self, amb_temp, wind_chill, solar_rad):
        temp_diff = self.current_temp - wind_chill
        loss_w = self.U * self.A * temp_diff
        
        window_area = self.A * 0.05
        solar_gain_w = solar_rad * window_area * 0.6
        
        internal_gain_w = self.volume_m3 * 2.0
        
        net_heat_w = solar_gain_w + internal_gain_w - loss_w
        return net_heat_w / 1000.0

class HVACModel:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        self.zones = {
            "LIVING": Zone("Living & Labs", 20.0, 5000, 0.15, 2000, 5000000, fault_manager),
            "GARAGE": Zone("Vehicle Garage", 5.0,  2000, 0.30, 1000, 2000000, fault_manager),
            "MEDICAL":Zone("Cold Storage",   4.0,  200,  0.10, 150,  300000, fault_manager),
            "SERVER": Zone("IT Server Room", 18.0, 300,  0.15, 200,  400000, fault_manager)
        }
        
        self.hrv_efficiency = 0.80
        self.glycol_specific_heat = 3.3 # kJ/kg.K for 57% Glycol-L
        
        # Physics State
        self.glycol_supply_temp_c = 15.0 # Set by CHP in previous tick
        self.glycol_return_temp_c = 15.0
        self.glycol_pressure_bar = 2.5
        
        self.dhw_tank_temp_c = 60.0
        self.legionella_risk = False
        
        # Timers
        self.airlock_timer = 0
        self.fume_hood_timer = 0
        
        self.total_heat_demand_kw = 0.0
        self.total_electrical_demand_kw = 0.0
        
        self.register_faults()
        
    def register_faults(self):
        fm = self.fault_manager
        fm.register_spof("HVAC_GLYCOL_PUMP_WEAR", "Pump loses pressure, poor flow")
        fm.register_spof("HVAC_GLYCOL_LEAK", "Catastrophic loss of glycol pressure")
        fm.register_spof("HVAC_AHU_FAN_FAIL", "Living zone blower motor failure")
        fm.register_spof("HVAC_DAMPER_STUCK", "Living zone fresh air damper stuck at 10%")
        fm.register_spof("HVAC_FILTER_CLOG", "Living zone air filter clogged")
        fm.register_spof("HVAC_SENSOR_DRIFT_TEMP", "Living zone thermostat reads 5C too high")
        fm.register_spof("HVAC_SENSOR_DRIFT_CO2", "Living zone CO2 sensor reads 400ppm flat")
        fm.register_spof("HVAC_DHW_VALVE_FAIL", "DHW thermal disinfection valve stuck closed")

    def get_air_density(self, temp_c):
        return 1.29 * (273.15 / (273.15 + temp_c))

    def update(self, state: dict, sim_time=None, dt: int = 1):
        if dt <= 0: dt = 1
            
        env = state.get("environment", {})
        amb_temp = env.get("ambient_temperature_c", -15.0)
        wind_chill = env.get("wind_chill_c", -20.0)
        solar_rad = env.get("solar_radiation_wm2", 0.0)
        
        # Read Supply Temp from CHP if available
        chp_state = state.get("power", {}).get("generators", {})
        running_chps = [c for c in chp_state.values() if c["state"] == "RUNNING"]
        if running_chps:
            # Assuming CHP heat exchanger targets 85C for supply when running
            chp_hx_temp = sum(c["coolant_temp_c"] for c in running_chps) / len(running_chps)
            # If CHP block is 90C, heat exchanger can output 85C max
            self.glycol_supply_temp_c = min(85.0, chp_hx_temp - 5.0)
        else:
            self.glycol_supply_temp_c = max(amb_temp, self.glycol_supply_temp_c - (0.01 * dt))

        fm = self.fault_manager
        
        # 0. Power Grid Check
        grid_status = state.get("power", {}).get("grid_status", "ONLINE")
        has_power = (grid_status == "ONLINE")
        
        total_heat_kw = 0.0
        total_elec_kw = 0.0
        
        # 1. FAULTS
        pump_wear = fm.is_fault_active("HVAC_GLYCOL_PUMP_WEAR")
        glycol_leak = fm.is_fault_active("HVAC_GLYCOL_LEAK")
        fan_fail = fm.is_fault_active("HVAC_AHU_FAN_FAIL")
        damper_stuck = fm.is_fault_active("HVAC_DAMPER_STUCK")
        filter_clog = fm.is_fault_active("HVAC_FILTER_CLOG")
        temp_drift = fm.is_fault_active("HVAC_SENSOR_DRIFT_TEMP")
        co2_drift = fm.is_fault_active("HVAC_SENSOR_DRIFT_CO2")
        dhw_fail = fm.is_fault_active("HVAC_DHW_VALVE_FAIL")
        
        # Glycol Pressure Physics
        target_pressure = 2.5 * (1.0 - (pump_wear * 0.4))
        if glycol_leak > 0: target_pressure = 0.1 # Absolute failure
        self.glycol_pressure_bar = target_pressure + random.gauss(0, 0.02)
        
        # 2. DYNAMIC EVENTS
        if 8 <= sim_time.hour <= 18:
            if self.airlock_timer <= 0 and random.random() < (0.001 * dt):
                self.airlock_timer = 300 
            if self.fume_hood_timer <= 0 and random.random() < (0.0005 * dt):
                self.fume_hood_timer = 3600 
                
        self.airlock_timer = max(0, self.airlock_timer - dt)
        self.fume_hood_timer = max(0, self.fume_hood_timer - dt)
        airlock_active = (self.airlock_timer > 0)
        fume_hood_active = (self.fume_hood_timer > 0)
        
        # 3. DHW & THERMAL DISINFECTION
        dhw_heat_loss_kw = 2.0 # Natural loss from tanks
        if dhw_fail == 0 and has_power:
            dhw_heating_kw = 15.0 # Max heater coil
            if self.dhw_tank_temp_c < 60.0:
                self.dhw_tank_temp_c += ((dhw_heating_kw - dhw_heat_loss_kw) * dt) / 500.0 # Thermal mass of tank
                total_heat_kw += dhw_heating_kw
        else:
            self.dhw_tank_temp_c -= (dhw_heat_loss_kw * dt) / 500.0
            
        self.legionella_risk = self.dhw_tank_temp_c < 55.0
        if self.legionella_risk:
            logging.warning("LEGIONELLA RISK: DHW Tank Temp fell below 55C!")

        # 4. LIVING ZONE: CO2 DCV
        living = self.zones["LIVING"]
        perceived_co2 = living.co2_ppm
        if co2_drift > 0: perceived_co2 = 400.0 # Sensor lies, says air is perfect

        if living.co2_ppm is not None:
            human_co2_generation = 0.2 * dt
            living.co2_ppm += human_co2_generation
            
            target_damper = 0.0
            if perceived_co2 > 800: target_damper = 100.0
            elif perceived_co2 > 500: target_damper = ((perceived_co2 - 500) / 300) * 100.0
            
            if damper_stuck > 0: target_damper = 10.0 # Physical actuator jammed
            if not has_power: target_damper = 0.0 # Spring-return closed on power fail
            
            # Actuator physics: Moves 2% per second
            if living.ahu.damper_open_pct < target_damper:
                living.ahu.damper_open_pct = min(target_damper, living.ahu.damper_open_pct + (2.0 * dt))
            elif living.ahu.damper_open_pct > target_damper:
                living.ahu.damper_open_pct = max(target_damper, living.ahu.damper_open_pct - (2.0 * dt))
                
            vent_factor = (living.ahu.damper_open_pct / 100.0) * (0.005 * dt)
            living.co2_ppm -= (living.co2_ppm - 400) * vent_factor

        max_air_volume = (living.volume_m3 * 1.0) / 3600.0
        actual_air_volume = max_air_volume * (living.ahu.damper_open_pct / 100.0)
        air_mass = actual_air_volume * self.get_air_density(amb_temp)
        effective_temp_diff = (living.current_temp - amb_temp) * (1.0 - self.hrv_efficiency)
        ventilation_heat_loss_kw = air_mass * 1.006 * effective_temp_diff
        
        fume_hood_loss_kw = 0.0
        if fume_hood_active and has_power:
            fume_air_mass = 0.5 * self.get_air_density(amb_temp) 
            fume_temp_diff = living.current_temp - amb_temp
            fume_hood_loss_kw = fume_air_mass * 1.006 * fume_temp_diff
            total_elec_kw += 5.0 
        ventilation_heat_loss_kw += fume_hood_loss_kw
        
        humidification_power_kw = 0.0
        heated_windows_kw = 0.0
        if has_power:
            humidification_power_kw = (air_mass * 0.005) * 2260.0
            total_elec_kw += humidification_power_kw
            
            heated_windows_kw = abs(min(0, amb_temp)) * 0.5 
            total_elec_kw += heated_windows_kw
            
            if airlock_active:
                total_heat_kw += 30.0 
                total_elec_kw += 2.0 
                
        # 5. ZONES & GLYCOL PHYSICS
        zone_data = {}
        total_mass_flow = 0.0
        heat_extracted = 0.0
        
        for name, zone in self.zones.items():
            net_passive_kw = zone.calculate_losses_gains(amb_temp, wind_chill, solar_rad)
            
            if name == "LIVING":
                net_passive_kw -= ventilation_heat_loss_kw 
            elif name == "SERVER":
                comms_heat_kw = state.get("communication", {}).get("heat_dissipation_kw", 25.0)
                net_passive_kw += comms_heat_kw 
                
            # Server Room Free Cooling Logic
            if name == "SERVER":
                if zone.current_temp > zone.target_temp:
                    zone.ahu.damper_open_pct = 100.0
                    fc_mass_flow = 2.0 * self.get_air_density(amb_temp)
                    free_cooling_kw = fc_mass_flow * 1.006 * (zone.current_temp - amb_temp)
                    net_passive_kw -= free_cooling_kw
                    total_elec_kw += 3.0 
                else:
                    zone.ahu.damper_open_pct = 0.0
            
            # Thermostat Drift Fault
            perceived_room_temp = zone.current_temp
            if name == "LIVING" and temp_drift > 0:
                perceived_room_temp += 5.0 # Thermostat falsely reads hotter
                
            error = zone.target_temp - perceived_room_temp
            max_kw = {"LIVING": 250.0, "GARAGE": 100.0, "MEDICAL": 15.0, "SERVER": 0.0}[name]
            
            if error > 0 and name != "SERVER":
                requested_kw = ((error * zone.thermal_mass) / dt) / 1000.0
                requested_kw += abs(net_passive_kw) 
                
                # Cannot extract heat if supply is cold or pressure is gone
                if self.glycol_supply_temp_c > zone.current_temp and self.glycol_pressure_bar > 0.5:
                    # PID Valve control (0-100%)
                    target_valve = min(100.0, (requested_kw / max_kw) * 100.0)
                    zone.glycol_valve_open_pct = (0.2 * target_valve) + (0.8 * zone.glycol_valve_open_pct)
                else:
                    zone.glycol_valve_open_pct = 0.0
            else:
                zone.glycol_valve_open_pct = 0.0
                
            # Actual Heat Transferred
            zone.heat_demand_kw = max_kw * (zone.glycol_valve_open_pct / 100.0)
            
            # Filter Clog Fault (Living only for now)
            if name == "LIVING":
                if filter_clog > 0:
                    zone.ahu.filter_health_pct = max(10.0, zone.ahu.filter_health_pct - (2.0 * dt))
                else:
                    zone.ahu.filter_health_pct = 100.0 # Replace filter instantly for ease
                    
            # Fan Fail Fault
            if not has_power:
                zone.ahu.fan_rpm = 0.0
                zone.heat_demand_kw = 0.0 # No air pushing = no heat transfer
            elif name == "LIVING" and fan_fail > 0:
                zone.ahu.fan_rpm = 0.0
                zone.heat_demand_kw = 0.0 
            elif zone.heat_demand_kw > 0:
                base_rpm = (zone.heat_demand_kw / max_kw) * 1500.0
                # Blower works harder if filter is clogged
                zone.ahu.fan_rpm = min(3000.0, base_rpm * (100.0 / max(1.0, zone.ahu.filter_health_pct)))
            else:
                zone.ahu.fan_rpm = 1500.0 if (name == "SERVER" and zone.ahu.damper_open_pct > 0) else 0.0
            
            temp_change_passive = ((net_passive_kw * 1000.0) * dt) / zone.thermal_mass
            temp_change_active = ((zone.heat_demand_kw * 1000.0) * dt) / zone.thermal_mass
            zone.current_temp += (temp_change_passive + temp_change_active)
            
            # Glycol Physics
            if zone.heat_demand_kw > 0:
                glycol_delta_t = 20.0
                zone.glycol_mass_flow_kg_s = zone.heat_demand_kw / (self.glycol_specific_heat * glycol_delta_t)
                total_mass_flow += zone.glycol_mass_flow_kg_s
                heat_extracted += zone.heat_demand_kw
            else:
                zone.glycol_mass_flow_kg_s = 0.0
                
            # AHU Thermodynamics (SAT/RAT)
            zone.ahu.return_air_temp_c = zone.current_temp
            if zone.heat_demand_kw > 0 and zone.ahu.fan_rpm > 0:
                # Approximate heating coil math
                zone.ahu.supply_air_temp_c = min(50.0, zone.current_temp + (zone.heat_demand_kw / 5.0))
            else:
                zone.ahu.supply_air_temp_c = zone.current_temp
                
            # Fan Affinity Law (Power scales with RPM cubed)
            fan_elec_kw = 2.0 * ((zone.ahu.fan_rpm / 1500.0) ** 3)
            total_elec_kw += fan_elec_kw
            total_heat_kw += zone.heat_demand_kw
            
            zone_data[name] = {
                "temp_c": round(zone.current_temp, 2),
                "perceived_temp_c": round(perceived_room_temp, 2) if name == "LIVING" else round(zone.current_temp, 2),
                "heat_demand_kw": round(zone.heat_demand_kw, 2),
                "ahu": {
                    "fan_rpm": int(zone.ahu.fan_rpm),
                    "filter_health_pct": round(zone.ahu.filter_health_pct, 1),
                    "damper_open_pct": round(zone.ahu.damper_open_pct, 1),
                    "glycol_flow_kg_s": round(zone.glycol_mass_flow_kg_s, 2),
                    "supply_air_temp_c": round(zone.ahu.supply_air_temp_c, 1),
                    "return_air_temp_c": round(zone.ahu.return_air_temp_c, 1)
                }
            }
            if zone.co2_ppm is not None:
                zone_data[name]["co2_ppm"] = round(zone.co2_ppm, 1)
                zone_data[name]["perceived_co2_ppm"] = round(perceived_co2, 1)

        # 6. Main Glycol Loop Return Temp calculation
        # Include wastewater heating demand (it pulls from the same glycol loop)
        wastewater_heat_kw = state.get("wastewater", {}).get("heat_demand_kw", 0.0)
        heat_extracted += wastewater_heat_kw
        total_heat_kw += wastewater_heat_kw
        
        # Additional mass flow required for wastewater heat exchanger
        if wastewater_heat_kw > 0:
            total_mass_flow += wastewater_heat_kw / (self.glycol_specific_heat * 20.0)
            
        pump_elec_kw = 0.0
        if has_power:
            pump_elec_kw = total_mass_flow * 0.7 * (2.5 / self.glycol_pressure_bar if self.glycol_pressure_bar > 0.1 else 1)
        total_elec_kw += pump_elec_kw
        
        if total_mass_flow > 0:
            avg_delta_t = heat_extracted / (total_mass_flow * self.glycol_specific_heat)
            self.glycol_return_temp_c = self.glycol_supply_temp_c - avg_delta_t
        else:
            self.glycol_return_temp_c = self.glycol_supply_temp_c
            
        # Radiative pipe loss
        self.glycol_return_temp_c = max(amb_temp, self.glycol_return_temp_c - 1.0)
            
        self.total_heat_demand_kw = total_heat_kw
        self.total_electrical_demand_kw = total_elec_kw
        
        state["hvac"] = {
            "total_heat_demand_kw": round(self.total_heat_demand_kw, 1),
            "total_electrical_demand_kw": round(self.total_electrical_demand_kw, 1),
            "glycol_supply_temp_c": round(self.glycol_supply_temp_c, 1),
            "glycol_return_temp_c": round(self.glycol_return_temp_c, 1),
            "glycol_pressure_bar": round(self.glycol_pressure_bar, 2),
            "dhw_tank_temp_c": round(self.dhw_tank_temp_c, 1),
            "legionella_risk": self.legionella_risk,
            "ventilation_loss_kw": round(ventilation_heat_loss_kw, 1),
            "humidification_load_kw": round(humidification_power_kw, 1),
            "heated_windows_kw": round(heated_windows_kw, 1),
            "active_events": {
                "airlock_active": airlock_active,
                "fume_hood_active": fume_hood_active
            },
            "zones": zone_data
        }
        return state

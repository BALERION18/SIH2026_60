import math
import random
import logging

class CommunicationModel:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        
        # Systems State
        self.electrical_demand_kw = 0.0
        self.heat_dissipation_kw = 0.0
        self.server_core_temp_c = 40.0 # Internal chassis temperature
        
        # AGEOS LEO Tracking (Earth Station)
        self.leo_pass_active = False
        self.leo_timer_s = 7200.0 # Time until next pass (approx 2 hours)
        self.leo_pass_duration_s = 600.0 # 10 minute pass
        self.leo_incoming_data_rate_gbps = 0.0
        self.radome_ice_thickness_mm = 0.0
        self.tracking_accuracy_pct = 100.0
        
        # SAN (Storage Area Network) Buffer
        self.san_capacity_gb = 50000.0 # 50 TB
        self.san_used_gb = 5000.0
        self.total_data_dropped_gb = 0.0 # Metric for science data lost forever
        
        # GEO Relay Link (to India)
        self.geo_bandwidth_mbps = 40.0
        self.geo_link_status = "ONLINE"
        
        # UPS (Uninterruptible Power Supply for Comms)
        self.ups_charge_pct = 100.0
        self.ups_capacity_kwh = 40.0
        
        self.register_faults()
        
    def register_faults(self):
        fm = self.fault_manager
        fm.register_spof("COMMS_RADOME_HEATER_FAIL", "Radome snow-melter fails, ice accumulates")
        fm.register_spof("COMMS_SERVO_MOTOR_JAM", "LEO dish azimuth/elevation motors jam")
        fm.register_spof("COMMS_GEO_LNB_FAIL", "Static GEO dish RF electronics fail")
        fm.register_spof("COMMS_SAN_DRIVE_FAIL", "SAN array drive fails, reducing capacity")
        fm.register_spof("COMMS_UPS_BATTERY_DEGRADE", "UPS batteries lose capacity")

    def update(self, state: dict, sim_time=None, dt: int = 1):
        if dt <= 0: dt = 1
        fm = self.fault_manager
        
        # Global dependencies
        env = state.get("environment", {})
        amb_temp = env.get("ambient_temperature_c", -15.0)
        wind_speed_ms = env.get("wind_speed_ms", 5.0)
        
        grid_status = state.get("power", {}).get("grid_status", "ONLINE")
        
        hvac = state.get("hvac", {})
        server_temp_c = hvac.get("zones", {}).get("SERVER", {}).get("temp_c", 20.0)
        
        # Faults
        heater_fail = fm.is_fault_active("COMMS_RADOME_HEATER_FAIL")
        servo_jam = fm.is_fault_active("COMMS_SERVO_MOTOR_JAM")
        geo_fail = fm.is_fault_active("COMMS_GEO_LNB_FAIL")
        san_fail = fm.is_fault_active("COMMS_SAN_DRIVE_FAIL")
        ups_degrade = fm.is_fault_active("COMMS_UPS_BATTERY_DEGRADE")
        
        self.electrical_demand_kw = 0.0
        self.heat_dissipation_kw = 0.0
        
        # --- 1. AGEOS LEO Tracking (Orbital Schedule) ---
        self.leo_timer_s -= dt
        
        if self.leo_timer_s <= 0:
            self.leo_pass_active = True
            self.leo_timer_s = self.leo_pass_duration_s
            self.leo_pass_duration_s = -1.0 # Flag that we are in a pass
            
        elif self.leo_pass_active and self.leo_timer_s <= 0:
            self.leo_pass_active = False
            self.leo_timer_s = 7200.0 + random.uniform(-600, 600) # Next pass in ~2 hours
            self.leo_pass_duration_s = 600.0
            
        # --- 2. Dynamic Power & Thermal Physics ---
        server_power_kw = 12.0
        servo_power_kw = 3.0
        heater_power_kw = 15.0
        
        servers_online = True
        
        # If server was already shutdown due to thermal trip, it needs to cool down to 50C to restart
        if hasattr(self, 'thermal_trip_active') and self.thermal_trip_active:
            if self.server_core_temp_c < 50.0:
                self.thermal_trip_active = False
            else:
                servers_online = False
                
        if servers_online and self.server_core_temp_c >= 70.0:
            servers_online = False
            self.thermal_trip_active = True
            
        thermal_throttle_pct = 0.0
        if servers_online and self.server_core_temp_c >= 60.0:
            thermal_throttle_pct = min(1.0, (self.server_core_temp_c - 60.0) / 10.0)
            
        # Server Internal Thermodynamics (Thermal Mass Delay)
        heat_generated_kw = server_power_kw if servers_online else 0.0
        # Heat transfer rate to the room air. At Delta=24C (44C core, 20C room), it dissipates 12kW.
        cooling_coefficient_kw_c = 0.5 
        
        heat_dissipated_to_room_kw = cooling_coefficient_kw_c * (self.server_core_temp_c - server_temp_c)
        net_heat_kw = heat_generated_kw - heat_dissipated_to_room_kw
        
        # Thermal mass of server racks (approx 500kg metal/components -> 450 kJ/K)
        server_thermal_mass_kj_k = 450.0
        self.server_core_temp_c += (net_heat_kw * dt) / server_thermal_mass_kj_k
        self.heat_dissipation_kw = max(0.0, heat_dissipated_to_room_kw) # Inject into HVAC SERVER zone
        
        actual_power_draw_kw = heat_generated_kw
            
        heater_running = False
        if heater_fail == 0 and (amb_temp < 5.0 or self.radome_ice_thickness_mm > 0):
            heater_running = True
            actual_power_draw_kw += heater_power_kw
            
        if self.leo_pass_active and servo_jam == 0:
            actual_power_draw_kw += servo_power_kw
            
        # UPS / Grid Dynamics
        actual_ups_capacity = self.ups_capacity_kwh * (1.0 - (ups_degrade * 0.8))
        system_powered = True
        
        if grid_status == "ONLINE":
            charge_rate_kw = 5.0
            self.electrical_demand_kw = actual_power_draw_kw + charge_rate_kw
            added_charge_kwh = (charge_rate_kw * dt) / 3600.0
            self.ups_charge_pct = min(100.0, self.ups_charge_pct + (added_charge_kwh / actual_ups_capacity) * 100.0)
        else:
            self.electrical_demand_kw = 0.0
            drained_kwh = (actual_power_draw_kw * dt) / 3600.0
            drain_pct = (drained_kwh / actual_ups_capacity) * 100.0
            self.ups_charge_pct = max(0.0, self.ups_charge_pct - drain_pct)
            
            if self.ups_charge_pct <= 0.0:
                system_powered = False
                
        # Total Blackout Cascades
        if not system_powered:
            servers_online = False
            heater_running = False
            self.heat_dissipation_kw = 0.0
            
        # --- 3. AGEOS Radome Weather Physics ---
        if heater_running:
            self.radome_ice_thickness_mm = max(0.0, self.radome_ice_thickness_mm - (0.05 * dt))
        elif amb_temp < -2.0 and env.get("state") == "BLIZZARD":
            self.radome_ice_thickness_mm += (0.01 * dt)
            
        # --- 4. Tracking Mechanics ---
        self.tracking_accuracy_pct = 100.0
        if self.leo_pass_active:
            if not system_powered or servo_jam > 0:
                self.tracking_accuracy_pct = 0.0
            else:
                wind_penalty = max(0, wind_speed_ms - 25.0) * 4.0
                self.tracking_accuracy_pct = max(0.0, 100.0 - wind_penalty)
                
        # --- 5. SAN Buffer Dynamics (Data Inflow) ---
        current_max_san_gb = self.san_capacity_gb
        if san_fail > 0:
            current_max_san_gb = self.san_capacity_gb * 0.4
            
        if self.san_used_gb > current_max_san_gb:
            lost = self.san_used_gb - current_max_san_gb
            self.total_data_dropped_gb += lost
            self.san_used_gb = current_max_san_gb
            
        self.leo_incoming_data_rate_gbps = 0.0
        if self.leo_pass_active:
            base_inflow_gbps = 2.0
            if servers_online:
                ice_penalty = min(1.0, self.radome_ice_thickness_mm / 15.0)
                tracking_multiplier = self.tracking_accuracy_pct / 100.0
                
                self.leo_incoming_data_rate_gbps = base_inflow_gbps * (1.0 - ice_penalty) * tracking_multiplier
                incoming_total_GB = (self.leo_incoming_data_rate_gbps / 8.0) * dt
                
                available_space = current_max_san_gb - self.san_used_gb
                added_gb = min(incoming_total_GB, available_space)
                self.san_used_gb += added_gb
                self.total_data_dropped_gb += (incoming_total_GB - added_gb)
            else:
                # If servers are dead during a pass, the data is completely lost!
                lost_data_GB = (base_inflow_gbps / 8.0) * dt
                self.total_data_dropped_gb += lost_data_GB
            
        # --- 6. GEO Relay Uplink (Data Outflow) ---
        self.geo_bandwidth_mbps = 0.0
        self.geo_link_status = "OFFLINE"
        
        if servers_online:
            if geo_fail > 0:
                self.geo_link_status = "LNB_FAULT"
            else:
                self.geo_link_status = "ONLINE"
                self.geo_bandwidth_mbps = 150.0 * (1.0 - thermal_throttle_pct)
                uplink_total_GB = (self.geo_bandwidth_mbps / 8192.0) * dt
                
                self.san_used_gb = max(0.0, self.san_used_gb - uplink_total_GB)
                
        # Status aggregation
        status = "NOMINAL"
        if not system_powered: status = "BLACKOUT_OFFLINE"
        elif not servers_online: status = "THERMAL_SHUTDOWN"
        elif self.san_used_gb >= current_max_san_gb * 0.95: status = "SAN_BUFFER_CRITICAL"
        elif thermal_throttle_pct > 0: status = "THERMAL_THROTTLING"
        
        state["communication"] = {
            "status": status,
            "geo_link_status": self.geo_link_status,
            "geo_bandwidth_mbps": round(self.geo_bandwidth_mbps, 2),
            "leo_pass_active": self.leo_pass_active,
            "leo_timer_s": int(self.leo_timer_s) if not self.leo_pass_active else 0,
            "leo_incoming_gbps": round(self.leo_incoming_data_rate_gbps, 2),
            "tracking_accuracy_pct": round(self.tracking_accuracy_pct, 1),
            "radome_ice_thickness_mm": round(self.radome_ice_thickness_mm, 1),
            "san_used_gb": int(self.san_used_gb),
            "san_capacity_gb": int(current_max_san_gb),
            "san_utilization_pct": round((self.san_used_gb / current_max_san_gb) * 100.0, 1),
            "total_data_dropped_gb": int(self.total_data_dropped_gb),
            "ups_charge_pct": round(self.ups_charge_pct, 1),
            "server_core_temp_c": round(self.server_core_temp_c, 1),
            "electrical_demand_kw": round(self.electrical_demand_kw, 1),
            "heat_dissipation_kw": round(self.heat_dissipation_kw, 1)
        }
        
        return state

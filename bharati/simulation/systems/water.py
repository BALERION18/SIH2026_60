import logging
import math

class WaterModel:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        
        # Intake & Physics
        self.seawater_temp_c = -1.8 # Southern Ocean temp
        self.intake_pipe_temp_c = -1.8
        self.intake_flow_L_s = 0.0
        self.heat_trace_active = True
        
        # Storage
        self.fresh_water_tank_L = 15000.0
        self.tank_capacity_L = 15000.0
        
        # Desalination State
        self.is_plant_running = False
        self.mmf_pressure_drop_bar = 0.5
        self.membrane_fouling_pct = 0.0
        self.hpp_pressure_bar = 60.0
        
        # Water Quality
        self.permeate_tds_ppm = 200.0
        self.permeate_ph = 7.0
        self.tank_tds_ppm = 200.0
        self.tank_ph = 7.2
        
        self.electrical_demand_kw = 0.0
        
        self.register_faults()
        
    def register_faults(self):
        fm = self.fault_manager
        fm.register_spof("WATER_INTAKE_HEAT_FAIL", "Seawater intake heat trace dies, pipe freezes")
        fm.register_spof("WATER_MMF_CLOG", "Multimedia sand filter clogged")
        fm.register_spof("WATER_DOSING_PUMP_FAIL", "Anti-scalant chemical pump fails")
        fm.register_spof("WATER_ERD_FAIL", "Energy Recovery Device jams (Massive kW spike)")
        fm.register_spof("WATER_RO_MEMBRANE_FOUL", "Gradual biological/mineral scaling")
        fm.register_spof("WATER_RO_MEMBRANE_TEAR", "Fouled membrane rips under pressure (TDS spike)")
        fm.register_spof("WATER_HPP_FAIL", "High Pressure Pump failure")
        fm.register_spof("WATER_REMINERALIZATION_FAIL", "Calcite filter depleted (Acidic pH)")
        fm.register_spof("WATER_TANK_LEAK", "Potable water tank rupture")

    def update(self, state: dict, sim_time=None, dt: int = 1):
        if dt <= 0: dt = 1
        
        fm = self.fault_manager
        intake_heat_fail = fm.is_fault_active("WATER_INTAKE_HEAT_FAIL")
        mmf_clog = fm.is_fault_active("WATER_MMF_CLOG")
        dosing_fail = fm.is_fault_active("WATER_DOSING_PUMP_FAIL")
        erd_fail = fm.is_fault_active("WATER_ERD_FAIL")
        membrane_foul = fm.is_fault_active("WATER_RO_MEMBRANE_FOUL")
        membrane_tear = fm.is_fault_active("WATER_RO_MEMBRANE_TEAR")
        hpp_fail = fm.is_fault_active("WATER_HPP_FAIL")
        remin_fail = fm.is_fault_active("WATER_REMINERALIZATION_FAIL")
        tank_leak = fm.is_fault_active("WATER_TANK_LEAK")
        
        self.electrical_demand_kw = 0.0
        
        # 0. Power Grid Check
        grid_status = state.get("power", {}).get("grid_status", "ONLINE")
        has_power = (grid_status == "ONLINE")
        
        # 1. Seawater Intake & Heat Tracing (Physics)
        # Seawater freezes at -2.0C. We must keep pipe > 0C to be safe.
        target_intake_temp = self.seawater_temp_c
        if intake_heat_fail == 0 and has_power:
            self.heat_trace_active = True
            target_intake_temp = 5.0 
            self.electrical_demand_kw += 12.0 # Intake heating
        else:
            self.heat_trace_active = False
            
        # Pipe thermal mass cooling/heating
        temp_diff = target_intake_temp - self.intake_pipe_temp_c
        cooling_rate = (temp_diff * dt) / 3600.0 # 1 hour to equalize
        self.intake_pipe_temp_c += cooling_rate
        
        intake_blocked = self.intake_pipe_temp_c <= -1.9 
        
        # 2. Plant Control Logic
        # Station consumes ~2000 L of water a day (0.023 L/s). 
        # Plant runs when tank < 10000L.
        consumption_L_s = 0.025
        if tank_leak > 0:
            consumption_L_s += 1.0 # 1 L/s massive leak
            
        self.fresh_water_tank_L = max(0.0, self.fresh_water_tank_L - (consumption_L_s * dt))
        
        if self.fresh_water_tank_L < 10000.0 and not intake_blocked and hpp_fail == 0 and has_power:
            self.is_plant_running = True
        elif self.fresh_water_tank_L >= self.tank_capacity_L or intake_blocked or hpp_fail > 0 or not has_power:
            self.is_plant_running = False
            
        # 3. Desalination Physics
        if self.is_plant_running:
            self.intake_flow_L_s = 1.0 # 1 L/s raw seawater
            
            # A. MMF Clog
            if mmf_clog > 0:
                self.mmf_pressure_drop_bar = min(5.0, self.mmf_pressure_drop_bar + (0.01 * dt))
            else:
                self.mmf_pressure_drop_bar = 0.5
                
            # B. Anti-Scalant Dosing & Fouling
            fouling_rate = 0.0001
            if membrane_foul > 0: fouling_rate *= 10.0 # Accelerated
            if dosing_fail > 0: fouling_rate *= 100.0 # Catastrophic scaling
            
            self.membrane_fouling_pct = min(100.0, self.membrane_fouling_pct + (fouling_rate * dt))
            
            # C. High Pressure Pump (HPP) & Energy Recovery (ERD)
            # To push 1L/s through a fouled membrane requires exponentially more pressure.
            base_pressure = 60.0
            fouling_penalty = (self.membrane_fouling_pct / 100.0) * 40.0 # up to +40 bar
            self.hpp_pressure_bar = base_pressure + fouling_penalty + self.mmf_pressure_drop_bar
            
            # Power calculation: P (kW) = (Q * H * 100) / (efficiency * 1000)
            raw_hpp_kw = ((self.intake_flow_L_s * self.hpp_pressure_bar * 100.0) / 0.85) / 1000.0
            
            if erd_fail == 0:
                # ERD recovers 60% of hydraulic energy from brine reject
                hpp_kw = raw_hpp_kw * 0.40
            else:
                # ERD jammed. HPP must do 100% of the work. Massive spike!
                hpp_kw = raw_hpp_kw
                
            self.electrical_demand_kw += hpp_kw
            
            # D. Membrane Tear & Water Quality
            product_flow_L_s = 0.4 # 40% recovery rate
            
            if membrane_tear > 0:
                # Membrane physically ripped. Raw seawater (35,000 ppm) passes through!
                self.permeate_tds_ppm = 35000.0 * 0.5 # Mixing
                product_flow_L_s = 0.8 # Less resistance
            else:
                # Normal rejection (99.4%)
                self.permeate_tds_ppm = 35000.0 * 0.006 
                
            # E. Remineralization
            if membrane_tear > 0:
                self.permeate_ph = 8.1 # Raw seawater pH overrides RO pH
            elif remin_fail > 0:
                self.permeate_ph = 5.5 # Acidic RO water
            else:
                self.permeate_ph = 7.2 # Healthy, remineralized
                
            # F. Tank Mixing Math (Industry level mass balance)
            new_water_L = product_flow_L_s * dt
            if self.fresh_water_tank_L + new_water_L > 0:
                # Weighted average for TDS
                total_tds = (self.fresh_water_tank_L * self.tank_tds_ppm) + (new_water_L * self.permeate_tds_ppm)
                self.tank_tds_ppm = total_tds / (self.fresh_water_tank_L + new_water_L)
                
                # True Logarithmic pH Mixing
                h_tank = (10 ** -self.tank_ph) * self.fresh_water_tank_L
                h_new = (10 ** -self.permeate_ph) * new_water_L
                h_total = h_tank + h_new
                h_concentration = h_total / (self.fresh_water_tank_L + new_water_L)
                
                # Prevent math domain error if h_concentration is 0 (which is physically impossible but mathematically possible in floats)
                if h_concentration > 0:
                    self.tank_ph = -math.log10(h_concentration)
                
            self.fresh_water_tank_L = min(self.tank_capacity_L, self.fresh_water_tank_L + new_water_L)
                
        else:
            self.intake_flow_L_s = 0.0
            self.hpp_pressure_bar = 0.0
            # Membrane doesn't magically clean itself when off
            
        state["water"] = {
            "tank_level_L": round(self.fresh_water_tank_L, 1),
            "is_running": self.is_plant_running,
            "intake_pipe_temp_c": round(self.intake_pipe_temp_c, 2),
            "intake_blocked": intake_blocked,
            "mmf_pressure_drop_bar": round(self.mmf_pressure_drop_bar, 2),
            "membrane_fouling_pct": round(self.membrane_fouling_pct, 1),
            "hpp_pressure_bar": round(self.hpp_pressure_bar, 1),
            "permeate_tds_ppm": int(self.permeate_tds_ppm),
            "tank_tds_ppm": int(self.tank_tds_ppm),
            "tank_ph": round(self.tank_ph, 2),
            "electrical_demand_kw": round(self.electrical_demand_kw, 1)
        }
        return state

import math
import random
import logging

class WastewaterModel:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        
        # Tank Capacities (Liters)
        self.greywater_tank_L = 1000.0
        self.technical_water_tank_L = 2000.0 # Treated greywater for toilet flushing
        self.blackwater_tank_L = 500.0       # Equalization
        self.mbr_tank_L = 2000.0             # Bioreactor
        self.sludge_tank_L = 0.0             # Excess bio-solids
        
        self.tank_max_L = {
            "grey": 5000.0,
            "tech": 5000.0,
            "black": 3000.0,
            "mbr": 5000.0,
            "sludge": 2000.0
        }
        
        # Biological & Chemical Physics
        self.mbr_temp_c = 15.0
        self.discharge_pipe_temp_c = 5.0 # Heat-traced pipe
        self.bacteria_health_pct = 100.0
        
        # Stateful Chemistry (Mass Balance)
        self.mbr_cod_mgL = 40.0         # Starts healthy
        self.mbr_ammonia_mgL = 1.0
        self.effluent_cod_mgL = 40.0      
        self.effluent_ammonia_mgL = 1.0   
        self.pathogen_alarm = False
        
        # Logistical Physics
        self.sludge_bags_available = 100
        self.uv_intensity_pct = 100.0
        
        self.electrical_demand_kw = 0.0
        self.heat_demand_kw = 0.0
        
        self.register_faults()
        
    def register_faults(self):
        fm = self.fault_manager
        # Bio/Chem
        fm.register_spof("WASTE_AERATION_BLOWER_FAIL", "Oxygen starvation in MBR")
        fm.register_spof("WASTE_TOXIC_SPILL", "Harsh chemicals sterilize bacteria")
        fm.register_spof("WASTE_GREYWATER_PUMP_FAIL", "Greywater equalization pump fails")
        # Madrid / Sludge
        fm.register_spof("WASTE_DEWATERING_CENTRIFUGE_FAIL", "Sludge thickener failure")
        fm.register_spof("WASTE_BAG_SHORTAGE", "No more bags for sludge repatriation")
        # Discharge
        fm.register_spof("WASTE_UV_LAMP_DEGRADE", "Gradual loss of UV disinfection")
        fm.register_spof("WASTE_UV_BALLAST_FAIL", "Complete UV failure")
        fm.register_spof("WASTE_DISCHARGE_FREEZE", "Ocean discharge heat-trace fails")

    def update(self, state: dict, sim_time=None, dt: int = 1):
        if dt <= 0: dt = 1
        fm = self.fault_manager
        
        # Global dependencies
        grid_status = state.get("power", {}).get("grid_status", "ONLINE")
        has_power = (grid_status == "ONLINE")
        
        env = state.get("environment", {})
        amb_temp = env.get("ambient_temperature_c", -15.0)
        
        hvac = state.get("hvac", {})
        glycol_temp_c = hvac.get("glycol_supply_temp_c", 15.0)
        
        self.electrical_demand_kw = 0.0
        self.heat_demand_kw = 0.0
        
        # Faults
        blower_fail = fm.is_fault_active("WASTE_AERATION_BLOWER_FAIL")
        toxic_spill = fm.is_fault_active("WASTE_TOXIC_SPILL")
        gw_pump_fail = fm.is_fault_active("WASTE_GREYWATER_PUMP_FAIL")
        centrifuge_fail = fm.is_fault_active("WASTE_DEWATERING_CENTRIFUGE_FAIL")
        bag_shortage = fm.is_fault_active("WASTE_BAG_SHORTAGE")
        uv_degrade = fm.is_fault_active("WASTE_UV_LAMP_DEGRADE")
        uv_fail = fm.is_fault_active("WASTE_UV_BALLAST_FAIL")
        freeze_fail = fm.is_fault_active("WASTE_DISCHARGE_FREEZE")
        
        # 1. Greywater Generation & Recycling Loop
        # Station sinks/showers generate continuous low flow, BUT ONLY if potable water exists!
        water_state = state.get("water", {})
        potable_tank_L = water_state.get("tank_level_L", 15000.0)
        
        greywater_inflow_L_s = 0.0
        if potable_tank_L > 0.0:
            greywater_inflow_L_s = 0.02
            
        self.greywater_tank_L = min(self.tank_max_L["grey"], self.greywater_tank_L + (greywater_inflow_L_s * dt))
        
        gw_transfer_L_s = 0.0
        # Float switch: Only run pump if source has water AND destination is not full
        if gw_pump_fail == 0 and has_power and self.greywater_tank_L > 0 and self.technical_water_tank_L < self.tank_max_L["tech"]:
            # Transfer and lightly treat greywater to technical water
            gw_transfer_L_s = 0.05
            self.electrical_demand_kw += 1.5 # Pump
        
        transfer_amt = gw_transfer_L_s * dt
        transfer_amt = min(transfer_amt, self.greywater_tank_L)
        transfer_amt = min(transfer_amt, self.tank_max_L["tech"] - self.technical_water_tank_L)
        
        self.greywater_tank_L -= transfer_amt
        self.technical_water_tank_L += transfer_amt
        
        # 2. Blackwater Generation (Dependent on Technical Water!)
        # Toilets use technical water. If technical tank is empty or blackwater is full, toilets can't flush!
        blackwater_inflow_L_s = 0.0
        if self.technical_water_tank_L > 0 and self.blackwater_tank_L < self.tank_max_L["black"]:
            blackwater_inflow_L_s = 0.01
            flush_amt = blackwater_inflow_L_s * dt
            flush_amt = min(flush_amt, self.technical_water_tank_L)
            
            # Strict Mass Conservation
            added_blackwater = flush_amt
            self.technical_water_tank_L -= flush_amt
            
            # Massive overload if toxic spill
            if toxic_spill > 0:
                toxic_amt = 0.05 * dt # Dumping chemicals
                added_blackwater += toxic_amt
                
            self.blackwater_tank_L = min(self.tank_max_L["black"], self.blackwater_tank_L + added_blackwater)
        
        # Transfer Blackwater to MBR
        bw_transfer_L_s = 0.0
        # Float switch: run if blackwater exists AND MBR has space
        if has_power and self.blackwater_tank_L > 0 and self.mbr_tank_L < self.tank_max_L["mbr"]:
            bw_transfer_L_s = 0.02
            self.electrical_demand_kw += 1.0 # Macerator / Transfer pump
            
        bw_amt = bw_transfer_L_s * dt
        bw_amt = min(bw_amt, self.blackwater_tank_L)
        bw_amt = min(bw_amt, self.tank_max_L["mbr"] - self.mbr_tank_L)
        
        self.blackwater_tank_L -= bw_amt
        self.mbr_tank_L += bw_amt
        
        # 3. HVAC Thermal Integration
        # MBR tank loses heat to ambient. Requires HVAC glycol to stay at 15C for bacteria.
        # Exponential cooling (Newton's Law) prevents overshoot at high time accelerations
        cooling_rate = 0.0005
        self.mbr_temp_c = amb_temp + (self.mbr_temp_c - amb_temp) * math.exp(-cooling_rate * dt)
        
        if self.mbr_temp_c < 15.0 and has_power:
            # Heat exchanger pulls heat from Glycol Loop
            if glycol_temp_c > self.mbr_temp_c + 5.0:
                self.heat_demand_kw = 15.0
                # Specific Heat Math: Prevent divide by zero
                mass_kg = max(100.0, self.mbr_tank_L) 
                heat_gain = (self.heat_demand_kw / (mass_kg * 4.18)) * dt
                self.mbr_temp_c = min(15.0, self.mbr_temp_c + heat_gain)
                
        # 4. Biology (Bacteria Health & Toxic Shock)
        if toxic_spill > 0:
            # Toxic chemical takes time to kill billions of bacteria (smooth drop)
            self.bacteria_health_pct = max(0.0, self.bacteria_health_pct - (1.5 * dt))
        else:
            aeration_ok = (has_power and blower_fail == 0)
            if aeration_ok:
                self.electrical_demand_kw += 5.0 # Air blowers
                # Bacteria recover if aerated and warm
                if self.mbr_temp_c >= 10.0:
                    self.bacteria_health_pct = min(100.0, self.bacteria_health_pct + (0.05 * dt))
                elif self.mbr_temp_c < 5.0:
                    self.bacteria_health_pct = max(0.0, self.bacteria_health_pct - (0.1 * dt)) # Cold shock
            else:
                self.bacteria_health_pct = max(0.0, self.bacteria_health_pct - (0.5 * dt)) # Asphyxiation
                
        # Sludge overflow kills bacteria
        if self.sludge_tank_L >= self.tank_max_L["sludge"]:
            self.bacteria_health_pct = max(0.0, self.bacteria_health_pct - (1.0 * dt))
            
        # 5. Sludge Dewatering (Madrid Protocol)
        # MBR process creates sludge based on ACTUAL mass transferred. 
        # This mass MUST be removed from MBR and added to Sludge tank (Mass Conservation)
        sludge_created = bw_amt * 0.05
        self.mbr_tank_L -= sludge_created
        self.sludge_tank_L += sludge_created
        
        centrate_return = 0.0
        # Interlock: Stop if manually faulted OR physically out of bags
        actual_bag_shortage = (bag_shortage > 0) or (self.sludge_bags_available <= 0)
        
        if has_power and centrifuge_fail == 0 and not actual_bag_shortage and self.sludge_tank_L > 100.0:
            self.electrical_demand_kw += 8.0 # Centrifuge
            dewater_rate_L_s = 0.1
            dewatered = dewater_rate_L_s * dt
            dewatered = min(dewatered, self.sludge_tank_L)
            self.sludge_tank_L -= dewatered
            
            # The centrifuge separates solid sludge from water.
            # Water (Centrate) is returned to the MBR! (~80% of wet sludge is water)
            centrate_return = dewatered * 0.8
            self.mbr_tank_L += centrate_return
            
            # Consume bags for the solid portion (1 bag per 50L of raw sludge)
            # Fix: Calculate exact fractional bags to support high dt scaling without random() bug
            bags_needed = dewatered / 50.0
            full_bags = int(bags_needed)
            fractional_bag = bags_needed - full_bags
            if random.random() < fractional_bag:
                full_bags += 1
            self.sludge_bags_available = max(0, self.sludge_bags_available - full_bags)
                
        # 6. Effluent Chemistry (Stateful Mass Balance Mixing)
        # Raw blackwater chemistry
        raw_cod = 800.0
        raw_ammonia = 80.0
        if toxic_spill > 0:
            raw_cod = 15000.0  # Massive chemical load injected into blackwater
            raw_ammonia = 500.0
            
        # Inflow Mixing Equation (Physical concentration math)
        # (Current Mass + Inflow Mass) / Total Volume
        if self.mbr_tank_L + bw_amt > 0:
            total_cod_mass = (self.mbr_cod_mgL * self.mbr_tank_L) + (raw_cod * bw_amt)
            total_ammonia_mass = (self.mbr_ammonia_mgL * self.mbr_tank_L) + (raw_ammonia * bw_amt)
            
            # Temporary concentration before bacteria eat it
            self.mbr_cod_mgL = total_cod_mass / (self.mbr_tank_L + bw_amt)
            self.mbr_ammonia_mgL = total_ammonia_mass / (self.mbr_tank_L + bw_amt)
            
        # Bacterial Digestion (Reduces COD continuously over time)
        # A healthy MBR can digest ~1.5 mg/L of COD per second.
        digestion_rate_cod = 1.5 * (self.bacteria_health_pct / 100.0) * dt
        digestion_rate_ammonia = 0.15 * (self.bacteria_health_pct / 100.0) * dt
        
        self.mbr_cod_mgL = max(40.0, self.mbr_cod_mgL - digestion_rate_cod) # Base floor of 40 mg/L
        self.mbr_ammonia_mgL = max(1.0, self.mbr_ammonia_mgL - digestion_rate_ammonia) # Base floor
        
        # Effluent is drawn directly from the mixed tank
        self.effluent_cod_mgL = self.mbr_cod_mgL
        self.effluent_ammonia_mgL = self.mbr_ammonia_mgL
        
        # UV Disinfection
        target_uv = 100.0
        if uv_degrade > 0: target_uv = 40.0
        if uv_fail > 0 or not has_power: target_uv = 0.0
        
        if self.uv_intensity_pct < target_uv:
            self.uv_intensity_pct = min(target_uv, self.uv_intensity_pct + (5.0 * dt))
        elif self.uv_intensity_pct > target_uv:
            self.uv_intensity_pct = max(target_uv, self.uv_intensity_pct - (5.0 * dt))
            
        if has_power and uv_fail == 0:
            self.electrical_demand_kw += 3.0 # UV Lamps
            
        # Alarm logic
        self.pathogen_alarm = self.uv_intensity_pct < 80.0
        self.chemical_alarm = self.effluent_cod_mgL > 50.0 or self.effluent_ammonia_mgL > 5.0
        
        # Heated discharge & Thermal Mass
        target_pipe_temp = amb_temp
        if freeze_fail == 0 and has_power:
            self.electrical_demand_kw += 6.0 # Heat trace
            target_pipe_temp = 5.0
            
        # Pipe thermal mass cooling/heating (Takes ~1-2 hours to equalize)
        pipe_cooling_rate = 0.0005
        self.discharge_pipe_temp_c = target_pipe_temp + (self.discharge_pipe_temp_c - target_pipe_temp) * math.exp(-pipe_cooling_rate * dt)
        
        discharge_blocked = self.discharge_pipe_temp_c <= -1.8
                
        # Compliance Interlock: Prevent illegal dumping
        discharge_valve_open = not discharge_blocked
        if uv_fail > 0 or not has_power:
            discharge_valve_open = False
                
        # Discharge flow (Level-controlled Pump)
        if discharge_valve_open:
            # Physical level control: Pump runs if tank is above 2000L nominal level
            if self.mbr_tank_L > 2000.0:
                discharge_pump_capacity = 0.05 * dt
                discharge_amt = min(discharge_pump_capacity, self.mbr_tank_L - 2000.0)
                self.mbr_tank_L -= discharge_amt

        state["wastewater"] = {
            "greywater_tank_L": round(self.greywater_tank_L, 1),
            "technical_water_tank_L": round(self.technical_water_tank_L, 1),
            "blackwater_tank_L": round(self.blackwater_tank_L, 1),
            "mbr_tank_L": round(self.mbr_tank_L, 1),
            "mbr_temp_c": round(self.mbr_temp_c, 1),
            "discharge_pipe_temp_c": round(self.discharge_pipe_temp_c, 1),
            "bacteria_health_pct": round(self.bacteria_health_pct, 1),
            "sludge_tank_L": round(self.sludge_tank_L, 1),
            "sludge_bags_available": self.sludge_bags_available,
            "effluent_cod_mgL": round(self.effluent_cod_mgL, 1),
            "effluent_ammonia_mgL": round(self.effluent_ammonia_mgL, 1),
            "uv_intensity_pct": round(self.uv_intensity_pct, 1),
            "pathogen_alarm": self.pathogen_alarm,
            "chemical_alarm": self.chemical_alarm,
            "discharge_frozen": discharge_blocked,
            "electrical_demand_kw": round(self.electrical_demand_kw, 1),
            "heat_demand_kw": round(self.heat_demand_kw, 1)
        }
        
        return state

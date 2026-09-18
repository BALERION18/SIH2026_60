import math
import random
import logging
from enum import Enum

class AssetReliability:
    """
    Industrial Weibull Distribution Engine for Mechanical Failure.
    Tracks Effective Age (t_eff) based on environmental stressors.
    """
    def __init__(self, asset_id: str, fault_manager, fault_to_trigger: str, beta: float, eta_hours: float):
        self.asset_id = asset_id
        self.fault_manager = fault_manager
        self.fault_to_trigger = fault_to_trigger
        
        # Weibull parameters
        self.beta = beta          # Shape parameter (wear-out > 1)
        self.eta = eta_hours      # Scale parameter (MTTF in hours)
        self.effective_age_hours = 0.0
        self.is_failed = False
        
    def add_stress_hours(self, dt_seconds: float, stress_multiplier: float):
        if not self.is_failed:
            self.effective_age_hours += (dt_seconds / 3600.0) * stress_multiplier
            
    def check_failure(self, dt_seconds: float) -> bool:
        """Evaluates the stochastic probability of failure in this tick."""
        if self.is_failed:
            return True
            
        # Weibull CDF: F(t) = 1 - exp(-(t/eta)^beta)
        try:
            f_t = 1.0 - math.exp(-1.0 * math.pow(self.effective_age_hours / self.eta, self.beta))
        except OverflowError:
            f_t = 1.0 # Guarantee failure if numbers get insanely large
            
        # Stochastic dice roll against the probability curve
        # Normally F(t) is lifetime probability, so instantaneous hazard rate is better,
        # but for simplicity in discrete simulation, we check if a random draw falls under a scaled F(t)
        # Hazard rate h(t) = (beta/eta) * (t/eta)^(beta-1)
        if self.effective_age_hours > 0:
            h_t = (self.beta / self.eta) * math.pow(self.effective_age_hours / self.eta, self.beta - 1)
            failure_prob_this_tick = h_t * (dt_seconds / 3600.0)
            
            if random.random() < failure_prob_this_tick:
                self.is_failed = True
                self.fault_manager.trigger(self.fault_to_trigger, severity=1.0)
                logging.critical(f"RELIABILITY ENGINE: {self.asset_id} suffered stochastic Weibull failure! (t_eff={self.effective_age_hours:.1f}h, h(t)={h_t:.6f})")
                return True
        return False
        
    def repair(self):
        """Resets the effective age after physical part replacement."""
        self.effective_age_hours = 0.0
        self.is_failed = False
        logging.info(f"RELIABILITY ENGINE: {self.asset_id} repaired. t_eff reset to 0.")


class PharmaceuticalInventory:
    """
    Arrhenius First-Order Kinetics for Molecular Degradation.
    """
    def __init__(self, name: str, initial_doses: int, Ea_joules: float, A_factor: float, mec_pct: float):
        self.name = name
        self.total_doses = initial_doses
        self.concentration_pct = 100.0
        self.Ea = Ea_joules
        self.A = A_factor
        self.mec_pct = mec_pct # Minimum Effective Concentration
        self.R = 8.314 # Universal Gas Constant (J/mol*K)
        
    def degrade(self, temp_c: float, dt_seconds: float):
        if self.concentration_pct <= 0.0:
            return
            
        temp_k = temp_c + 273.15
        
        # Cold Chain Phase Destruction (Freezing liquid meds destroys them)
        if temp_k < 273.15:
            self.concentration_pct = 0.0
            logging.critical(f"SPOILAGE: {self.name} froze at {temp_c:.1f}C! Complete molecular destruction.")
            return
            
        # Arrhenius Kinetics (Above freezing)
        # k = A * exp(-Ea / RT)
        k = self.A * math.exp(-self.Ea / (self.R * temp_k))
        
        # First-order decay: C(t) = C(0) * exp(-k*t)
        self.concentration_pct = self.concentration_pct * math.exp(-k * dt_seconds)
        
        if self.concentration_pct < self.mec_pct and self.concentration_pct > 0.0:
            self.concentration_pct = 0.0
            logging.critical(f"SPOILAGE: {self.name} fell below MEC ({self.mec_pct}%). Stock mathematically useless.")


class InventoryModel:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        self.occupancy = 25
        
        # 1. Assets tracking Weibull reliability
        self.assets = {
            "CHP1_FUEL_PUMP": AssetReliability("CHP1_FUEL_PUMP", fault_manager, "CHP-1_FUEL_PUMP_FAIL", beta=2.5, eta_hours=20000.0),
            "RO_MEMBRANE": AssetReliability("RO_MEMBRANE", fault_manager, "WATER_RO_MEMBRANE_CLOG", beta=3.0, eta_hours=5000.0),
            "HVAC_FILTERS": AssetReliability("HVAC_FILTERS", fault_manager, "HVAC_FILTER_CLOG", beta=2.0, eta_hours=4000.0)
        }
        
        # 2. Medical / Chemical Stocks (Ea and A factors tuned for realism)
        # Insulin: Highly sensitive. Ea ~ 100 kJ/mol. A factor tuned so it degrades ~1% per month at 5C, but very fast at 25C.
        self.pharma = {
            "INSULIN": PharmaceuticalInventory("INSULIN", initial_doses=1000, Ea_joules=100000.0, A_factor=1.5e10, mec_pct=90.0),
            "ADRENALINE": PharmaceuticalInventory("ADRENALINE", initial_doses=200, Ea_joules=80000.0, A_factor=2.0e6, mec_pct=85.0)
        }
        
        # 3. Dry Goods & Caloric Tracking
        self.food_kg = 15000.0
        
        # 4. ERP Master Data (Bill of Materials)
        self.spares = {
            "FUEL_PUMP_SEALS": 2,
            "RO_MEMBRANE_CARTRIDGES": 3,
            "HVAC_AIR_FILTERS": 10
        }
        
        # 5. Maintenance Queue (MTTR System)
        self.active_repairs = []
        self.current_time = None
        
    def dispatch_work_order(self, fault_id: str, state: dict = None) -> bool:
        """
        Enterprise Resource Planning (ERP) Interlock.
        Attempts to resolve a fault physically using the Bill of Materials.
        """
        # fault_id -> (req_part, asset_id, base_mttr_hours)
        mapping = {
            "CHP-1_FUEL_PUMP_FAIL": ("FUEL_PUMP_SEALS", "CHP1_FUEL_PUMP", 4.0),
            "WATER_RO_MEMBRANE_CLOG": ("RO_MEMBRANE_CARTRIDGES", "RO_MEMBRANE", 8.0),
            "HVAC_FILTER_CLOG": ("HVAC_AIR_FILTERS", "HVAC_FILTERS", 2.0)
        }
        
        if fault_id not in mapping:
            # Fault doesn't require a tracked spare part, but still takes a base time to fix (e.g. 2 hours)
            hrp = state.get("human", {}).get("hrp", 1.0) if state else 1.0
            mttr_seconds = (2.0 * 3600.0) * max(1.0, (2.0 - hrp))
            
            if self.current_time:
                from datetime import timedelta
                completion_time = self.current_time + timedelta(seconds=mttr_seconds)
                self.active_repairs.append({
                    "fault_id": fault_id,
                    "asset_id": None,
                    "completion_time": completion_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "duration_hours": round(mttr_seconds/3600.0, 1)
                })
                logging.info(f"WORK ORDER QUEUED: {fault_id} requires {mttr_seconds/3600.0:.1f} hours to repair (HRP: {hrp:.2f}).")
            else:
                self.fault_manager.resolve(fault_id)
            return True
            
        req_part, asset_id, base_mttr_hours = mapping[fault_id]
        
        # Check if already queued to prevent duplicate part consumption
        for r in self.active_repairs:
            if r["fault_id"] == fault_id:
                logging.warning(f"WORK ORDER REJECTED: {fault_id} is already actively being repaired.")
                return False
        
        if self.spares.get(req_part, 0) > 0:
            hrp = state.get("human", {}).get("hrp", 1.0) if state else 1.0
            if random.random() > hrp:
                self.spares[req_part] -= 1
                logging.critical(f"HUMAN ERROR: Mechanic botched the {req_part} replacement due to extreme fatigue/cold! Part wasted.")
                return False
                
            self.spares[req_part] -= 1
            
            # Queue the repair asynchronously instead of instantly fixing it
            mttr_seconds = (base_mttr_hours * 3600.0) * max(1.0, (2.0 - hrp))
            
            if self.current_time:
                from datetime import timedelta
                completion_time = self.current_time + timedelta(seconds=mttr_seconds)
                self.active_repairs.append({
                    "fault_id": fault_id,
                    "asset_id": asset_id,
                    "completion_time": completion_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "duration_hours": round(mttr_seconds/3600.0, 1)
                })
                logging.info(f"WORK ORDER QUEUED: {req_part} installed. System {fault_id} will be functional in {mttr_seconds/3600.0:.1f} hours.")
            else:
                self.fault_manager.resolve(fault_id)
                if asset_id in self.assets:
                    self.assets[asset_id].repair()
                    
            return True
        else:
            logging.error(f"WORK ORDER REJECTED: Insufficient stock of {req_part} to fix {fault_id}!")
            return False

    def calculate_caloric_burn(self, wind_chill_c: float, ambient_c: float, dt: float) -> float:
        """Calculates metabolic food depletion based on thermal homeostasis."""
        # BMR is ~2500 kcal/day (104.1 kcal/hr)
        base_kcal_s = (2500.0 / 86400.0) * self.occupancy
        
        # Cold stress adds caloric demand if exposed. Assuming 20% of crew is outside.
        outside_crew = self.occupancy * 0.2
        cold_penalty_kcal_s = 0.0
        if wind_chill_c < -10.0:
            # Exponential shivering thermogenesis penalty
            cold_penalty_kcal_s = outside_crew * (10.0 * math.exp(-0.05 * (wind_chill_c + 10.0))) / 3600.0
            
        total_kcal_s = base_kcal_s + cold_penalty_kcal_s
        # 1 kg of mixed dry/frozen rations = ~3500 kcal
        food_burn_kg = (total_kcal_s * dt) / 3500.0
        return food_burn_kg

    def update(self, state: dict, sim_time=None, dt: int = 1):
        if dt <= 0: dt = 1
        self.current_time = sim_time
        
        # --- MTTR REPAIR QUEUE PROCESSING ---
        if self.current_time:
            from datetime import datetime, timezone
            completed_repairs = []
            for repair in self.active_repairs:
                # Parse the ISO string back to datetime for comparison
                comp_dt = datetime.strptime(repair["completion_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                if self.current_time >= comp_dt:
                    # Repair duration has elapsed, formally resolve the fault
                    self.fault_manager.resolve(repair["fault_id"])
                    if repair["asset_id"] and repair["asset_id"] in self.assets:
                        self.assets[repair["asset_id"]].repair()
                    completed_repairs.append(repair)
                    logging.info(f"WORK ORDER COMPLETED: {repair['fault_id']} is fully repaired and online.")
            
            # Remove completed repairs from queue
            for r in completed_repairs:
                self.active_repairs.remove(r)
        
        env = state.get("environment", {})
        wind_chill = env.get("wind_chill_c", -20.0)
        ambient_c = env.get("ambient_temperature_c", -15.0)
        
        # 1. Update Caloric / Food Stock
        food_burn = self.calculate_caloric_burn(wind_chill, ambient_c, dt)
        self.food_kg = max(0.0, self.food_kg - food_burn)
        
        # 2. Update Pharmacokinetics (Arrhenius)
        med_temp_c = state.get("hvac", {}).get("zones", {}).get("MEDICAL", {}).get("temp_c", 5.0)
        for med_id, med in self.pharma.items():
            med.degrade(med_temp_c, dt)
            
        # 3. Update Weibull Asset Reliability Engine
        # Track physical stressors from other modules
        fuel_visc = state.get("fuel", {}).get("viscosity_cSt", 2.0)
        pump_stress = max(1.0, math.pow(fuel_visc / 5.0, 2)) # Quadratic stress curve for pumps pushing sludge
        self.assets["CHP1_FUEL_PUMP"].add_stress_hours(dt, pump_stress)
        
        ro_pressure = state.get("water", {}).get("transmembrane_pressure_bar", 40.0)
        ro_stress = max(1.0, math.exp(0.1 * (ro_pressure - 40.0))) # Exponential stress for high pressure
        self.assets["RO_MEMBRANE"].add_stress_hours(dt, ro_stress)
        
        air_dust = 2.0 if env.get("state") == "BLIZZARD" else 1.0 # High snow/dust ingestion
        self.assets["HVAC_FILTERS"].add_stress_hours(dt, air_dust)
        
        for asset in self.assets.values():
            asset.check_failure(dt)
            
        # Compile Telemetry
        state["inventory"] = {
            "food_stock_kg": round(self.food_kg, 1),
            "pharma": {
                name: {
                    "concentration_pct": round(med.concentration_pct, 2),
                    "doses_available": med.total_doses if med.concentration_pct > 0 else 0
                } for name, med in self.pharma.items()
            },
            "spares": self.spares.copy(),
            "reliability_effective_age_hours": {
                asset_id: round(asset.effective_age_hours, 1) for asset_id, asset in self.assets.items()
            },
            "active_repairs": self.active_repairs
        }
        
        return state

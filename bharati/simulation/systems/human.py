import math
import random
import logging
from datetime import datetime

class ThermalComfortEngine:
    """ASHRAE 55 PMV (Predicted Mean Vote) Calculator."""
    def __init__(self):
        self.metabolic_rate_met = 1.2 # Standing, light activity
        self.clo = 1.0 # Winter indoor clothing
        
    def calculate_pmv(self, temp_c: float, rh_pct: float, air_vel_ms: float = 0.1) -> float:
        """
        Calculates PMV using an industrial approximation of Fanger's equation 
        valid for indoor conditions between 5C and 30C.
        Returns a float between -3.0 (Cold) and +3.0 (Hot).
        """
        # Constrain variables to prevent math overflow in extreme anomalies
        temp_c = max(-20.0, min(50.0, temp_c))
        rh_pct = max(0.0, min(100.0, rh_pct))
        
        # Saturated vapor pressure (kPa)
        p_sat = 0.611 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
        # Partial vapor pressure (Pa)
        p_a = (rh_pct / 100.0) * p_sat * 1000.0
        
        # Metabolic rate in W/m2 (1 met = 58.2 W/m2)
        M = self.metabolic_rate_met * 58.2
        W = 0.0 # External work
        
        # Clothing insulation (1 clo = 0.155 m2K/W)
        I_cl = self.clo * 0.155
        f_cl = 1.0 + 0.2 * self.clo if self.clo <= 0.5 else 1.05 + 0.1 * self.clo
        
        # Convective heat transfer coeff approx
        h_c = 12.1 * math.sqrt(max(0.1, air_vel_ms))
        
        # Mean radiant temp approx equal to air temp in an insulated building
        t_r = temp_c
        
        # Iterative calculation for clothing surface temp (Approximated to avoid slow loops)
        t_cl = temp_c + (35.5 - temp_c) / (3.5 * I_cl + 0.1)
        
        # Bio-heat losses
        # Radiant
        R = 3.96e-8 * f_cl * (math.pow(t_cl + 273.15, 4) - math.pow(t_r + 273.15, 4))
        # Convective
        C = f_cl * h_c * (t_cl - temp_c)
        # Sweating
        E_sw = 0.42 * ((M - W) - 58.15) if (M - W) > 58.15 else 0.0
        # Latent respiration
        E_re = 1.7e-5 * M * (5867.0 - p_a)
        # Sensible respiration
        C_re = 0.0014 * M * (34.0 - temp_c)
        # Skin diffusion
        E_diff = 3.05e-3 * (5733.0 - 6.99 * (M - W) - p_a)
        
        # Thermal Load (L)
        L = (M - W) - E_diff - E_sw - E_re - C_re - R - C
        
        # PMV
        pmv = (0.303 * math.exp(-0.036 * M) + 0.028) * L
        
        # Hard limits
        return max(-3.5, min(3.5, pmv))


class CircadianRhythmEngine:
    """Borbély's Two-Process Model for Sleep Regulation and SAD."""
    def __init__(self):
        self.process_s = 0.0 # Homeostatic sleep pressure (0 to 1)
        self.fatigue_index = 0.0
        self.melatonin_level = 0.0
        
    def update(self, dt: float, sim_time: datetime, solar_radiation: float):
        # Time of day normalized to 0-24
        hour_of_day = sim_time.hour + (sim_time.minute / 60.0)
        
        # Solar radiation suppresses melatonin
        # If Solar > 200 W/m2, melatonin is suppressed to 0. 
        # If Solar is 0 (Polar Night), melatonin remains high during the day.
        suppression = min(1.0, solar_radiation / 200.0)
        target_melatonin = 1.0 - suppression
        
        # Melatonin normally spikes at night (e.g. 10 PM to 6 AM)
        if hour_of_day < 6 or hour_of_day > 22:
            target_melatonin = 1.0
            
        # Exponential smoothing for hormone buildup
        self.melatonin_level += (target_melatonin - self.melatonin_level) * (dt / 3600.0)
        
        # Process C (Circadian Oscillator). Usually a sine wave driven by melatonin phase.
        # Amplitude dampens if melatonin is constantly high (SAD during Polar Night).
        amplitude = 1.0 if self.melatonin_level < 0.5 else 0.2
        process_c = amplitude * math.sin((2 * math.pi / 24.0) * (hour_of_day - 6.0))
        
        # Process S (Sleep Pressure). Builds up linearly over 16 hours awake, drops exponentially in 8 hours sleep.
        is_asleep = (hour_of_day < 6 or hour_of_day >= 22)
        if is_asleep:
            self.process_s *= math.exp(-0.5 * (dt / 3600.0))
        else:
            self.process_s += (1.0 / 16.0) * (dt / 3600.0)
            
        self.process_s = max(0.0, min(1.0, self.process_s))
        
        # Fatigue is high when sleep pressure is high AND circadian rhythm is low (or flattened)
        base_fatigue = self.process_s - process_c
        
        # Normalize fatigue to 0.0 - 1.0
        self.fatigue_index = max(0.0, min(1.0, (base_fatigue + 1.0) / 2.0))


class BioreactorStoichiometry:
    """Exact chemical outputs of human respiration."""
    def __init__(self):
        # 1 met = 58.2 W/m2. Average surface area = 1.8 m2. Total = 104.7 W per person
        self.watts_per_person = 104.7 
        
    def get_outputs(self, occupancy: int, pmv: float):
        # Shivering thermogenesis increases metabolic rate if PMV is very low
        met_multiplier = 1.0
        if pmv < -1.0:
            met_multiplier = 1.0 + (abs(pmv) * 0.2)
            
        total_watts = occupancy * self.watts_per_person * met_multiplier
        
        # Approximate: 30% Latent (Breath/Sweat), 70% Sensible (Body heat) at normal conditions
        latent_heat_w = total_watts * 0.3
        sensible_heat_w = total_watts * 0.7
        
        # Exact Stoichiometry: C6H12O6 + 6O2 -> 6CO2 + 6H2O + 2800 kJ/mol
        # Energy produced = total_watts (Joules/sec)
        moles_glucose_per_sec = total_watts / 2800000.0
        moles_co2_per_sec = moles_glucose_per_sec * 6.0
        
        # Ideal Gas Law at standard indoor temp (~20C) to volume (Liters)
        # V = nRT/P = (n * 8.314 * 293.15) / 101325 (m3) = * 1000 Liters
        # Simplified: 1 mole of gas at 20C = ~24.4 Liters
        co2_liters_sec = moles_co2_per_sec * 24.4
        
        return {
            "latent_heat_w": latent_heat_w,
            "sensible_heat_w": sensible_heat_w,
            "co2_l_s": co2_liters_sec
        }


class HumanAssetModel:
    def __init__(self, fault_manager):
        self.fault_manager = fault_manager
        self.thermal_engine = ThermalComfortEngine()
        self.circadian_engine = CircadianRhythmEngine()
        self.bio_engine = BioreactorStoichiometry()
        
        self.occupancy = 25
        self.pmv = 0.0
        self.hrp = 1.0 # Human Reliability Probability
        
    def update(self, state: dict, sim_time: datetime, dt: int = 1):
        if dt <= 0: dt = 1
        
        # 1. Update Occupancy (Summer vs Winter)
        month = sim_time.month
        self.occupancy = 50 if month in [11, 12, 1, 2] else 25
        
        # 2. Extract telemetry
        env = state.get("environment", {})
        solar_rad = env.get("solar_radiation_wm2", 0.0)
        
        hvac_zones = state.get("hvac", {}).get("zones", {})
        living_temp = hvac_zones.get("LIVING", {}).get("temp_c", 20.0)
        living_rh = hvac_zones.get("LIVING", {}).get("humidity_pct", 40.0)
        
        # 3. Calculate Engines
        self.pmv = self.thermal_engine.calculate_pmv(living_temp, living_rh)
        self.circadian_engine.update(dt, sim_time, solar_rad)
        
        outputs = self.bio_engine.get_outputs(self.occupancy, self.pmv)
        
        # 4. Human Reliability Probability (HRP)
        # HRP drops if PMV is extremely cold/hot, or if fatigue is very high
        thermal_penalty = math.pow(abs(self.pmv) / 3.0, 2) * 0.5 # Max 0.5 penalty
        fatigue_penalty = self.circadian_engine.fatigue_index * 0.5 # Max 0.5 penalty
        
        self.hrp = max(0.01, 1.0 - thermal_penalty - fatigue_penalty)
        
        # 5. Fault Injection (Frostbite/Trauma)
        if env.get("state") == "BLIZZARD" and env.get("wind_chill_c", 0.0) < -40.0:
            if random.random() < (0.0001 * dt):
                self.fault_manager.trigger("HUMAN_FROSTBITE", severity=1.0)
                logging.critical("MEDICAL EMERGENCY: Crew member suffered Frostbite during Blizzard ops!")
                
        # 6. Publish State
        state["human"] = {
            "occupancy": self.occupancy,
            "pmv": round(self.pmv, 2),
            "fatigue_index": round(self.circadian_engine.fatigue_index, 2),
            "hrp": round(self.hrp, 2),
            "co2_l_s": round(outputs["co2_l_s"], 4),
            "latent_heat_w": round(outputs["latent_heat_w"], 1),
            "sensible_heat_w": round(outputs["sensible_heat_w"], 1)
        }
        
        return state

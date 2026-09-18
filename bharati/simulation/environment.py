import random
import logging
import math
from datetime import datetime

class EnvironmentModel:
    def __init__(self):
        # 1. Empirical Monthly Profiles (Bharati Station)
        # Based on IMD data. Diurnal amplitudes are strictly 1.0 - 1.5 C.
        self.monthly_profiles = {
            1: {"mean": -2.0, "diurnal_amp": 1.5, "base_wind": 4.0},   # Summer
            2: {"mean": -5.0, "diurnal_amp": 1.5, "base_wind": 5.0},
            3: {"mean": -10.0, "diurnal_amp": 1.5, "base_wind": 8.0},
            4: {"mean": -14.0, "diurnal_amp": 1.2, "base_wind": 10.0},
            5: {"mean": -16.0, "diurnal_amp": 1.0, "base_wind": 15.0},  # Windiest month
            6: {"mean": -17.0, "diurnal_amp": 1.0, "base_wind": 12.0},  # Winter
            7: {"mean": -18.0, "diurnal_amp": 1.0, "base_wind": 14.0},
            8: {"mean": -17.0, "diurnal_amp": 1.0, "base_wind": 12.0},
            9: {"mean": -19.0, "diurnal_amp": 1.2, "base_wind": 10.0},  # Coldest month
            10: {"mean": -15.0, "diurnal_amp": 1.5, "base_wind": 8.0},
            11: {"mean": -8.0, "diurnal_amp": 1.5, "base_wind": 6.0},
            12: {"mean": -3.0, "diurnal_amp": 1.5, "base_wind": 4.0}
        }
        
        self.current_state = "CLEAR"
        
        # 2. Seasonal Markov Matrices
        self.transition_matrices = {
            "SUMMER": { # Dec, Jan, Feb
                "CLEAR":     {"CLEAR": 0.85, "CLOUDY": 0.10, "HIGH_WIND": 0.05, "BLIZZARD": 0.00},
                "CLOUDY":    {"CLEAR": 0.30, "CLOUDY": 0.60, "HIGH_WIND": 0.10, "BLIZZARD": 0.00},
                "HIGH_WIND": {"CLEAR": 0.20, "CLOUDY": 0.20, "HIGH_WIND": 0.60, "BLIZZARD": 0.00},
                "BLIZZARD":  {"CLEAR": 0.50, "CLOUDY": 0.00, "HIGH_WIND": 0.50, "BLIZZARD": 0.00} # Very rare
            },
            "WINTER": { # Jun, Jul, Aug, May, Sep
                "CLEAR":     {"CLEAR": 0.60, "CLOUDY": 0.15, "HIGH_WIND": 0.20, "BLIZZARD": 0.05},
                "CLOUDY":    {"CLEAR": 0.10, "CLOUDY": 0.60, "HIGH_WIND": 0.20, "BLIZZARD": 0.10},
                "HIGH_WIND": {"CLEAR": 0.05, "CLOUDY": 0.10, "HIGH_WIND": 0.55, "BLIZZARD": 0.30},
                "BLIZZARD":  {"CLEAR": 0.00, "CLOUDY": 0.05, "HIGH_WIND": 0.25, "BLIZZARD": 0.70} # Frequent blizzards
            },
            "TRANSITION": { # Mar, Apr, Oct, Nov
                "CLEAR":     {"CLEAR": 0.75, "CLOUDY": 0.15, "HIGH_WIND": 0.10, "BLIZZARD": 0.00},
                "CLOUDY":    {"CLEAR": 0.20, "CLOUDY": 0.60, "HIGH_WIND": 0.18, "BLIZZARD": 0.02},
                "HIGH_WIND": {"CLEAR": 0.10, "CLOUDY": 0.20, "HIGH_WIND": 0.60, "BLIZZARD": 0.10},
                "BLIZZARD":  {"CLEAR": 0.00, "CLOUDY": 0.20, "HIGH_WIND": 0.40, "BLIZZARD": 0.40}
            }
        }
        
        # 3. Physical State Modifiers (Multipliers based on monthly base wind)
        self.state_physics = {
            "CLEAR":     {"pressure_offset": 5.0,  "wind_mult": 1.0, "temp_offset": 0.0},
            "CLOUDY":    {"pressure_offset": -5.0, "wind_mult": 1.2, "temp_offset": 1.0}, # Clouds insulate
            "HIGH_WIND": {"pressure_offset": -15.0,"wind_mult": 2.5, "temp_offset": -3.0},
            "BLIZZARD":  {"pressure_offset": -35.0,"wind_mult": 4.5, "temp_offset": -8.0} # Intense drop
        }
        
        self.current_temp = -15.0
        self.current_wind = 5.0
        self.current_pressure = 995.0
        self.current_humidity = 60.0
        
        self.LATITUDE = -69.4
        self.alpha_1s = 0.0005 
        
        self.last_eval_time = None
        self.demo_override_temp = None

    def trigger_demo_event(self, target_temp):
        self.demo_override_temp = target_temp

    def release_demo_event(self):
        self.demo_override_temp = None

    def get_season(self, month):
        if month in [12, 1, 2]: return "SUMMER"
        if month in [5, 6, 7, 8, 9]: return "WINTER"
        return "TRANSITION"

    def evaluate_markov_chain(self, sim_time: datetime):
        if self.last_eval_time is None:
            self.last_eval_time = sim_time
            return
            
        if (sim_time - self.last_eval_time).total_seconds() >= 3600:
            self.last_eval_time = sim_time
            season = self.get_season(sim_time.month)
            matrix = self.transition_matrices[season]
            
            rand = random.random()
            cumulative = 0.0
            for next_state, prob in matrix[self.current_state].items():
                cumulative += prob
                if rand <= cumulative:
                    if next_state != self.current_state:
                        logging.info(f"[{season}] WEATHER EVENT: {self.current_state} -> {next_state}")
                        self.current_state = next_state
                    break

    def calculate_solar_radiation(self, sim_time: datetime) -> float:
        day_of_year = sim_time.timetuple().tm_yday
        hour = sim_time.hour + (sim_time.minute / 60.0)
        declination = 23.45 * math.sin(math.radians(360.0 * (284 + day_of_year) / 365.0))
        hour_angle = 15.0 * (hour - 12.0)
        
        lat_rad = math.radians(self.LATITUDE)
        dec_rad = math.radians(declination)
        ha_rad = math.radians(hour_angle)
        
        sin_elevation = math.sin(lat_rad) * math.sin(dec_rad) + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
        elevation = math.degrees(math.asin(sin_elevation))
        
        if elevation <= 0: return 0.0
        
        cloud_factor = {"CLEAR": 1.0, "CLOUDY": 0.4, "HIGH_WIND": 0.8, "BLIZZARD": 0.1}[self.current_state]
        radiation = 1000.0 * sin_elevation * cloud_factor
        return max(0.0, radiation)

    def calculate_wind_chill(self, temp_c: float, wind_ms: float) -> float:
        wind_kmh = wind_ms * 3.6
        if temp_c >= 10.0 or wind_kmh <= 4.8: return temp_c
        return 13.12 + 0.6215 * temp_c - 11.37 * (wind_kmh**0.16) + 0.3965 * temp_c * (wind_kmh**0.16)

    def update(self, state: dict, sim_time: datetime, dt: int):
        self.evaluate_markov_chain(sim_time)
        
        month_profile = self.monthly_profiles[sim_time.month]
        base_temp = month_profile["mean"]
        base_wind = month_profile["base_wind"]
        
        # 4. Morning Katabatic Winds (Between 4 AM and 9 AM local)
        is_katabatic = False
        katabatic_wind_spike = 0.0
        katabatic_temp_drop = 0.0
        
        if 4 <= sim_time.hour <= 9:
            # Consistent random chance based on the specific day (so it lasts the whole morning if triggered)
            day_seed = sim_time.year * 1000 + sim_time.timetuple().tm_yday
            random.seed(day_seed)
            if random.random() < 0.30: # 30% chance of Katabatic wind active during these hours
                is_katabatic = True
                katabatic_wind_spike = 15.0 # Adds 15 m/s
                katabatic_temp_drop = -4.0  # Drops 4 degrees
            random.seed() # reset seed to normal
            
        diurnal_offset = month_profile["diurnal_amp"] * math.sin(math.pi * (sim_time.hour - 8) / 12)
        
        physics = self.state_physics[self.current_state]
        
        # Calculate Targets
        target_temp = base_temp + diurnal_offset + physics["temp_offset"] + katabatic_temp_drop
        
        # Wind is base * state_multiplier + katabatic spike
        target_wind = (base_wind * physics["wind_mult"]) + katabatic_wind_spike
        target_wind = min(41.0, target_wind) # Cap wind to 41 m/s (80 knots) max observed
        
        # Base pressure around 985 hPa
        target_pressure = 985.0 + physics["pressure_offset"]
        
        # Apply Micro-Noise
        target_temp += random.gauss(0, 0.1)
        target_wind = max(0.0, target_wind + random.gauss(0, 0.5))
        target_pressure += random.gauss(0, 0.2)
        
        # Smooth with DT
        alpha_dt = 1.0 - (1.0 - self.alpha_1s) ** dt
        if self.demo_override_temp is not None:
            target_temp = self.demo_override_temp
            alpha_dt = 0.05 
            
        self.current_temp = (alpha_dt * target_temp) + ((1 - alpha_dt) * self.current_temp)
        self.current_wind = (alpha_dt * target_wind) + ((1 - alpha_dt) * self.current_wind)
        self.current_pressure = (alpha_dt * target_pressure) + ((1 - alpha_dt) * self.current_pressure)
        
        solar_rad = self.calculate_solar_radiation(sim_time)
        wind_chill = self.calculate_wind_chill(self.current_temp, self.current_wind)
        
        target_humidity = 100 - (self.current_temp + 30) * 1.5
        target_humidity = max(40.0, min(100.0, target_humidity))
        self.current_humidity = (alpha_dt * target_humidity) + ((1 - alpha_dt) * self.current_humidity)
        
        if "environment" not in state:
            state["environment"] = {}
            
        env = state["environment"]
        env["state"] = self.current_state
        env["katabatic_active"] = is_katabatic
        env["ambient_temperature_c"] = round(self.current_temp, 2)
        env["wind_chill_c"] = round(wind_chill, 2)
        env["wind_speed_ms"] = round(self.current_wind, 2)
        env["pressure_hpa"] = round(self.current_pressure, 1)
        env["humidity_percent"] = round(self.current_humidity, 1)
        env["solar_radiation_wm2"] = round(solar_rad, 1)
        
        return state

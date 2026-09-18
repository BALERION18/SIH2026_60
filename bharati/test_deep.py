import sys
import json
import logging
from simulation.engine import SimulationEngine
from simulation.environment import EnvironmentModel
from datetime import datetime, timedelta

# Suppress standard logging to avoid spam
logging.getLogger().setLevel(logging.ERROR)

def run_stress_test():
    engine = SimulationEngine(use_real_clock=False, time_acceleration=1)
    
    # Force extreme conditions
    engine.environment_model.current_temp = -45.0
    engine.environment_model.current_wind = 30.0 # Extreme blizzard
    
    ticks_to_run = 86400 # 24 hours of 1-second ticks
    
    print(f"Starting 24-hour stress test (1-second dt)...")
    for i in range(ticks_to_run):
        try:
            state = engine.step()
            
            # Spot check some constraints
            vehicles = state.get("vehicles", {}).get("fleet", {})
            for vid, v in vehicles.items():
                if v["battery_soc_pct"] > 100.0 or v["battery_soc_pct"] < 0.0:
                    raise ValueError(f"Battery SOC out of bounds: {v['battery_soc_pct']}")
                
                # Check for NaNs
                import math
                if math.isnan(v["engine_block_temp_c"]):
                    raise ValueError("engine_block_temp_c is NaN")
                    
        except Exception as e:
            print(f"FAILED on tick {i}: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
    print("SUCCESS: Simulator ran for 24 simulated hours (86,400 ticks) with 0 errors!")
    print("Final vehicle state:")
    print(json.dumps(state.get("vehicles", {}), indent=2))

if __name__ == "__main__":
    run_stress_test()

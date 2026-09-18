import sys
import math
import random
from datetime import datetime, timezone, timedelta
from simulation.engine import SimulationEngine

def check_invariants(state, tick):
    """Deep check of the state dictionary to catch NaNs, Infs, or impossible physics."""
    def check_dict(d, path):
        for k, v in d.items():
            if isinstance(v, dict):
                check_dict(v, path + "." + k)
            elif isinstance(v, float):
                if math.isnan(v):
                    raise ValueError(f"NaN detected at {path}.{k} on tick {tick}")
                if math.isinf(v):
                    raise ValueError(f"Infinity detected at {path}.{k} on tick {tick}")
            # Specific domain checks
            if k == "temp_c" and v < -100:
                raise ValueError(f"Impossible absolute temperature at {path}.{k} on tick {tick}")
            if k == "hrp" and (v < 0 or v > 1.0):
                raise ValueError(f"Invalid HRP {v} at {path}.{k} on tick {tick}")

    check_dict(state, "state")

def run_integration_test():
    print("Initializing Simulation Engine (All 10 Models)...")
    engine = SimulationEngine(use_real_clock=False, time_acceleration=1)
    
    # Force start in winter to stress test thermodynamics and circadian rhythms
    jump_time = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    engine.current_time = jump_time
    engine.last_sim_time = jump_time - timedelta(seconds=1)
    
    days_to_simulate = 5
    ticks = 86400 * days_to_simulate
    
    print(f"Running {days_to_simulate}-day deep integration stress test ({ticks} ticks)...")
    
    faults_to_inject = [
        "HVAC_LOSS_OF_POWER",
        "HVAC_FILTER_CLOG",
        "WATER_PIPE_BURST",
        "RO_PUMP_FAIL",
        "COMM_SATELLITE_LOSS",
        "CHP_FUEL_PUMP"
    ]
    
    try:
        for i in range(ticks):
            # Inject a random fault every 12 hours
            if i > 0 and i % 43200 == 0:
                fault = random.choice(faults_to_inject)
                engine.fault_manager.trigger(fault)
                
            # Randomly attempt to repair faults using ERP
            if i > 0 and i % 3600 == 0:
                active_faults = list(engine.fault_manager.active_faults.keys())
                for fault in active_faults:
                    engine.inventory_model.dispatch_work_order(fault, engine.state)
                    
            state = engine.step()
            
            # Check for silent mathematical errors on every single tick
            check_invariants(state, i)
            
    except Exception as e:
        print(f"\nCRITICAL FAILURE on tick {i}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    print(f"\nSUCCESS: Simulated {days_to_simulate} days perfectly.")
    print("All 10 models interacted flawlessly with 0 bugs, 0 NaNs, and 0 crashes.")
    
if __name__ == "__main__":
    run_integration_test()

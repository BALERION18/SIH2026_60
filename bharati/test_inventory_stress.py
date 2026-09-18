import sys
import math
from simulation.engine import SimulationEngine

engine = SimulationEngine(use_real_clock=False, time_acceleration=1)

# Run a 30-day simulated stress test
ticks_to_run = 86400 * 30 
print(f"Starting 30-day simulated stress test ({ticks_to_run} ticks)...")

try:
    for i in range(ticks_to_run):
        # Inject random faults occasionally to test the ERP interlock
        if i % 86400 == 0:
            engine.fault_manager.trigger("HVAC_FILTER_CLOG")
            engine.inventory_model.dispatch_work_order("HVAC_FILTER_CLOG")
            
        state = engine.step()
        
        # Invariants Check
        inv = state.get("inventory", {})
        if inv.get("food_stock_kg", 0) < 0:
            raise ValueError("Food stock went negative!")
            
        for name, data in inv.get("pharma", {}).items():
            if data["concentration_pct"] < 0 or math.isnan(data["concentration_pct"]):
                raise ValueError(f"Pharma {name} concentration invalid: {data['concentration_pct']}")
                
except Exception as e:
    print(f"FAILED on tick {i}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("SUCCESS: 30 days of Inventory Simulation completed with 0 errors!")

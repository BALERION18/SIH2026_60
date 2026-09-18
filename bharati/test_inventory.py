import sys
import json
from simulation.engine import SimulationEngine

engine = SimulationEngine(use_real_clock=False, time_acceleration=1)

print("--- Test 1: Arrhenius Spoilage (MEDICAL freeze) ---")
engine.environment_model.current_temp = -50.0
# Force HVAC failure to cause Medical Zone to freeze
engine.fault_manager.trigger("HVAC_LOSS_OF_POWER")

# Run for 1 hour simulation
for _ in range(3600):
    state = engine.step()

inventory_state = state.get("inventory", {})
pharma = inventory_state.get("pharma", {})
print("Pharma State after 1 hour of HVAC failure:")
print(json.dumps(pharma, indent=2))
if pharma["INSULIN"]["concentration_pct"] == 0:
    print("SUCCESS: Insulin denatured successfully below 0C!")
else:
    print("FAIL: Insulin did not denature!")

print("\n--- Test 2: ERP Interlock (Fixing the HVAC) ---")
# There are 10 HVAC filters in inventory initially, but this is a power loss, not a filter clog.
# Let's trigger a filter clog to test interlock.
engine.fault_manager.trigger("HVAC_FILTER_CLOG")
print("Attempting to fix HVAC_FILTER_CLOG with ERP Interlock...")
success = engine.inventory_model.dispatch_work_order("HVAC_FILTER_CLOG")
print(f"Repair successful: {success}")
print(f"Remaining Filters: {engine.inventory_model.spares['HVAC_AIR_FILTERS']}")

print("\n--- Test 3: Weibull Stress (Fuel Pump) ---")
# Run for a few more hours and check effective age
for _ in range(3600 * 5):
    state = engine.step()
    
print("Effective Age after 5 hours:")
print(json.dumps(state["inventory"]["reliability_effective_age_hours"], indent=2))

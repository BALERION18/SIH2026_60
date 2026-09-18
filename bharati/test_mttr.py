import sys
import time
from simulation.engine import SimulationEngine
from datetime import datetime, timezone, timedelta

engine = SimulationEngine(use_real_clock=False, time_acceleration=1)

print("--- MTTR Physics Test ---")
engine.current_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
engine.last_sim_time = engine.current_time - timedelta(seconds=1)

# Run one tick to initialize current_time in inventory
engine.step()

# Trigger a major fault
fault = "HVAC_FILTER_CLOG"
# HVAC_FILTER_CLOG requires a part and base MTTR is 2.0 hours.
engine.fault_manager.trigger(fault)

print(f"Tick 0: Fault {fault} active? {engine.fault_manager.is_fault_active(fault)}")

# Dispatch mechanic (loop until success in case of HRP human error)
success = False
while not success:
    success = engine.inventory_model.dispatch_work_order(fault, engine.state)
    
print(f"After dispatch, is fault STILL active? {engine.fault_manager.is_fault_active(fault)}")
if engine.fault_manager.is_fault_active(fault) > 0:
    print("SUCCESS: Fault is NOT instantly resolved! MTTR Queue is working.")
else:
    print("FAIL: Fault instantly resolved.")
    sys.exit(1)

# Advance time by 1 hour (3600 seconds)
engine.step()
engine.current_time += timedelta(hours=1)
engine.step()

print(f"After 1 hour, is fault STILL active? {engine.fault_manager.is_fault_active(fault)}")

# Advance time by another 4.0 hours (total 5.0 hours, surpassing the 3.4+ MTTR)
engine.current_time += timedelta(hours=4, minutes=0)
engine.step()

if engine.fault_manager.is_fault_active(fault) == 0:
    print("SUCCESS: Fault resolved automatically after 2+ hours of MTTR completion.")
else:
    print("FAIL: Fault did not resolve after MTTR time elapsed.")

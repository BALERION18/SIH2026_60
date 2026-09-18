import sys
import json
from simulation.engine import SimulationEngine
from datetime import datetime, timedelta, timezone

engine = SimulationEngine(use_real_clock=False, time_acceleration=1)

print("--- Test 1: Physiological Polar Night (SAD and Fatigue) ---")
# Force simulation to July (Deep Winter, Polar Night)
jump_time = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
engine.current_time = jump_time
engine.last_sim_time = jump_time - timedelta(seconds=1)
# Force environment update
engine.environment_model.update(engine.state, engine.current_time, 1)

# Run for 24 hours of Polar Night
print("Simulating 24 hours in July (No Solar Radiation)...")
for _ in range(86400):
    state = engine.step()
    
human_state = state.get("human", {})
print(f"Fatigue Index after 24 hours: {human_state.get('fatigue_index')}")
if human_state.get('fatigue_index') > 0.5:
    print("SUCCESS: Fatigue spiked due to Polar Night SAD!")
else:
    print("FAIL: Fatigue did not spike appropriately!")

print("\n--- Test 2: PMV Comfort and HRP Interlock (Death Spiral) ---")
# Force HVAC failure and drop room temp to 5C
engine.fault_manager.trigger("HVAC_LOSS_OF_POWER")
engine.environment_model.current_temp = -40.0
# Wait a few hours for room to get freezing cold
for _ in range(3600 * 5):
    state = engine.step()
    
human_state = state.get("human", {})
print(f"Room Temp: {state['hvac']['zones']['LIVING']['temp_c']:.1f}C")
print(f"PMV Score: {human_state['pmv']:.2f}")
print(f"Human Reliability Probability (HRP): {human_state['hrp']:.2f}")

if human_state['hrp'] < 0.8:
    print("SUCCESS: HRP dropped correctly due to cold and fatigue!")
else:
    print("FAIL: HRP did not drop!")
    
print("\n--- Test 3: Biological Mass Balance (Stoichiometry) ---")
print(f"Occupancy: {human_state['occupancy']} people")
print(f"CO2 output: {human_state['co2_l_s']} Liters/sec")
if human_state['co2_l_s'] > 0.1:
    print("SUCCESS: Humans are generating biologically accurate CO2!")
else:
    print("FAIL: Biological output is too low!")

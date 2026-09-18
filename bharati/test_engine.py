import sys
import json
from simulation.engine import SimulationEngine

engine = SimulationEngine(use_real_clock=False, time_acceleration=3600)
try:
    for i in range(3):
        state = engine.step()
        print(f"Tick {i} completed. Vehicles state:")
        print(json.dumps(state.get("vehicles", {}), indent=2))
    print("SUCCESS: Engine ran without errors.")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

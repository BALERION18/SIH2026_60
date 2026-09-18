import json
import logging
import os

class FaultManager:
    """
    Centralized Fault Registry and Injection Controller ("God Mode").
    Manages all Single Points of Failure (SPOFs) across the station.
    """
    def __init__(self):
        self.active_faults = {}
        self.registered_spofs = {}
    
    def register_spof(self, fault_id: str, description: str):
        """Called by components to register what can fail."""
        self.registered_spofs[fault_id] = description
        
    def trigger(self, fault_id: str, severity: float = 1.0):
        """Trigger an instant or transient fault out-of-band."""
        if fault_id not in self.registered_spofs:
            logging.warning(f"FaultManager: Unknown fault {fault_id}")
            return
            
        self.active_faults[fault_id] = severity
        logging.critical(f"FAULT INJECTED: {fault_id} (Severity: {severity})")

    def resolve(self, fault_id: str):
        """Resolve a fault."""
        if fault_id in self.active_faults:
            del self.active_faults[fault_id]
            logging.info(f"FAULT RESOLVED: {fault_id}")

    def is_fault_active(self, fault_id: str) -> float:
        """Returns severity if active, 0.0 otherwise. Used by physics models."""
        return self.active_faults.get(fault_id, 0.0)

    # --- TIME-JUMPING (STATE SNAPSHOT) METHODS ---
    
    def save_snapshot(self, engine_state: dict, filepath: str):
        """Saves the entire simulation state to a JSON file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(engine_state, f, indent=4)
            logging.info(f"Snapshot saved to {filepath}")
        except Exception as e:
            logging.error(f"Failed to save snapshot: {e}")

    def load_snapshot(self, filepath: str) -> dict:
        """Loads a pre-aged state for live ML demonstration."""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    state = json.load(f)
                logging.info(f"Loaded snapshot from {filepath}")
                return state
            else:
                logging.error(f"Snapshot file not found: {filepath}")
                return None
        except Exception as e:
            logging.error(f"Failed to load snapshot: {e}")
            return None

import time
import os
import sys
import json
from datetime import datetime
from simulation.engine import SimulationEngine

# ANSI Escape Codes for Colors
class C:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def format_value(v):
    if isinstance(v, float):
        return f"{v:,.3f}"
    return str(v)

def print_module_dynamic(title, data_dict, color):
    print(f"{color}{C.BOLD}>> {title.upper()} MODULE TELEMETRY <<{C.RESET}")
    if not data_dict:
        print("  [No telemetry available]")
        return
        
    def walk_dict(d, indent=2):
        for k, v in d.items():
            k_str = str(k).replace("_", " ").title()
            if isinstance(v, dict):
                print(" " * indent + f"{C.BOLD}[{k_str}]{C.RESET}")
                walk_dict(v, indent + 4)
            else:
                # Add units dynamically if known
                unit = ""
                if "temp" in k.lower() or "chill" in k.lower(): unit = " °C"
                elif "kw" in k.lower() or "power" in k.lower(): unit = " kW"
                elif "l_s" in k.lower() or "rate" in k.lower(): unit = " L/s"
                elif "wm2" in k.lower() or "radiation" in k.lower(): unit = " W/m²"
                elif "pct" in k.lower() or "percent" in k.lower(): unit = " %"
                elif "ppm" in k.lower(): unit = " PPM"
                elif "ms" in k.lower() and "speed" in k.lower(): unit = " m/s"
                
                val_str = format_value(v)
                print(" " * indent + f"{k_str:<30} : {C.CYAN}{val_str}{unit}{C.RESET}")

    walk_dict(data_dict)
    print("-" * 80)

def main():
    print(f"{C.CYAN}Initializing Ultra-High Fidelity 10-Module Bharati Digital Twin...{C.RESET}")
    engine = SimulationEngine(use_real_clock=False, time_acceleration=1)
    
    try:
        while True:
            state = engine.step()
            clear_console()
            
            print(f"{C.BOLD}{C.MAGENTA}" + "="*80)
            print(f"               BHARATI STATION DIGITAL TWIN - RAW TELEMETRY CORE               ")
            print("="*80 + f"{C.RESET}")
            print(f"{C.YELLOW}System Timestamp:{C.RESET} {state.get('timestamp')}    |    {C.YELLOW}Engine Tick:{C.RESET} {engine.tick_count}\n")
            
            # Print Every Single Module Dynamically (Prevents None/Missing Data Errors)
            # This ensures EVERY mathematically calculated variable is displayed in full depth!
            
            if "environment" in state: print_module_dynamic("Environment & Meteorology", state["environment"], C.CYAN)
            if "power" in state: print_module_dynamic("Power Grid & BESS", state["power"], C.YELLOW)
            if "hvac" in state: print_module_dynamic("HVAC Thermodynamics", state["hvac"], C.BLUE)
            if "fuel" in state: print_module_dynamic("Fuel (ATF) & Viscosity Physics", state["fuel"], C.RED)
            if "water" in state: print_module_dynamic("Water & RO Desalination", state["water"], C.CYAN)
            if "wastewater" in state: print_module_dynamic("Wastewater & MBR Bioreactor", state["wastewater"], C.GREEN)
            if "human" in state: print_module_dynamic("Human Asset & Physiology", state["human"], C.MAGENTA)
            if "inventory" in state: print_module_dynamic("Inventory & Asset Reliability (Weibull)", state["inventory"], C.YELLOW)
            if "vehicles" in state: print_module_dynamic("Vehicle Fleet (Thermodynamics)", state["vehicles"], C.BLUE)
            if "communication" in state: print_module_dynamic("Communication Link", state["communication"], C.CYAN)
            
            # Faults Section
            faults = state.get("faults", {})
            print(f"{C.RED}{C.BOLD}>> ACTIVE FAULTS / ALARMS <<{C.RESET}")
            if not faults:
                print(f"  {C.GREEN}[SYSTEM NOMINAL] No active faults detected.{C.RESET}")
            else:
                for f, details in faults.items():
                    print(f"  {C.RED}>> CRITICAL ALARM: {f} | Severity: {details.get('severity')}{C.RESET}")
            
            print(f"\n{C.BOLD}" + "="*80 + f"{C.RESET}")
            print(f"{C.YELLOW}Press CTRL+C to halt simulation engine.{C.RESET}")
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print(f"\n{C.RED}Simulation halted by user.{C.RESET}")
        sys.exit(0)

if __name__ == "__main__":
    main()

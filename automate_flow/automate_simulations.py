"""
 This script should run multiple SUMO simulations (with inner simulations considered as days), change user acceptance
 rates regarding a policy (public transport adoption), generate csv output files and aggregate TripInfo + emissions information
 into a single CSV with simulation_id, simulation_day, and policy_id columns for ease of use

"""

# ------------------ Imports ---------------------- #

import os
from pathlib import Path
import pandas as pd 

# Fetches all utility and extra import data
from automate_utils import *



from pathlib import Path

netfile = Path(r"D:\Rafa\A1 Mestrado\Obsidian-Masters-Degree\1o Ano\MS\automate_sumo\core\manhattan.net.xml")
print(netfile.exists(), netfile)

# ------------------ SUMO Setup ------------------- #

# Set SUMO binary (either 'sumo' or full path)
# Can change to 'sumo-gui' for visualization
SUMO_BINARY = os.environ.get("SUMO_BINARY", "sumo")  
CWD = os.getcwd()
SUMO_NET_FILE = CWD+"\\core\\"+"manhattan.net.xml"


 
# --------------- Directories Setup --------------- #

OUT_DIR = Path("sumo_runs")
FLOWS_DIR = OUT_DIR / "flows"
RAW_OUT_DIR = OUT_DIR / "raw_xml"
AGGREGATED_CSV = OUT_DIR / "aggregated_tripinfo_emissions.csv"
SUMMARY_CSV = OUT_DIR / "summary_per_run.csv"
for d in (OUT_DIR, FLOWS_DIR, RAW_OUT_DIR): d.mkdir(parents=True, exist_ok=True)


# --------------- Global Variables --------------- #

# Total number of people
PEOPLE_GLOBAL = 200  

# Default vehicle types and edge IDs
PRIVATE_VTYPE = "car"   

# TODO: Still undefined, haven't created flows for this yet
PUBLIC_VTYPE = "bus"     

# Simulation runtime per "day" (seconds) 
SIM_RUNTIME = 24 * 3600  # 24h in seconds 

if __name__ == "__main__":
    # TODO: replace edges with actual values after manually creating in netedit
    sumo_flows = {
    "private_flows": [
        # Private vehicle flow: cars using route "r_upper"
        # ["A4B4", "B4C4", "C4D4", "D4E4", "E4E3" ,"E3E2" ,"E2D2"] might not work as list
        ("flow_0", "A4B4 B4C4 C4D4 D4E4 E4E3 E3E2 E2D2", 0, SIM_RUNTIME, 1.0),  # 100% of private flow
    ],
    "public_flows": [
        # Public transport flow: buses using route "bus"
        ("flow_1", "A2A3 A3B3 B3C3 C3C2 C2C1 C1C0 C0B0", 0, SIM_RUNTIME, 1.0),  # 100% of public flow
    ],
}

    # Example policy: logistic adoption reaching 80% after a few days
    my_policy = {"id": "policy_bus_subsidy", "type": "logistic", "L": 0.8, "k": 0.8, "x0": 3}

    runSim(n_simulations=1 ,days_per_sim=7, policy=my_policy,
            num_agents_global=PEOPLE_GLOBAL,  flows_template=sumo_flows)

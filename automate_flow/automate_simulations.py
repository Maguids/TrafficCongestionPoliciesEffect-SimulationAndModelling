"""
 This script should run multiple SUMO simulations (with inner simulations considered as days), change user acceptance
 rates regarding a policy (public transport adoption), generate csv output files and aggregate TripInfo + emissions information
 into a single CSV with simulation_id, simulation_day, and policy_id columns for ease of use

"""

# ------------------ Imports ---------------------- #

import os
from pathlib import Path

# Fetches all utility and extra import data
from automate_utils import runSim, csvCleaner

BASE = Path(__file__).resolve().parent
SUMO_NET_FILE = (BASE / "core" / "manhattan.net.xml").resolve()
ADDITIONAL_FILES = [(BASE / "core" / "manhattan.add.xml").resolve()]

# ------------------ SUMO Setup ------------------- #

# Set SUMO binary (either 'sumo' or full path)
# Can change to 'sumo-gui' for visualization
SUMO_BINARY = os.environ.get("SUMO_BINARY", "sumo")  

# --------------- Directories Setup --------------- #

OUT_DIR = Path("sumo_runs")
FLOWS_DIR = OUT_DIR / "flows"
RAW_OUT_DIR = OUT_DIR / "raw_xml"
CSV_OUT_DIR = OUT_DIR / "raw_csv"
AGGREGATED_CSV = OUT_DIR / "aggregated_tripinfo_emissions.csv"
SUMMARY_CSV = OUT_DIR / "summary_per_run.csv"
for d in (OUT_DIR, FLOWS_DIR, RAW_OUT_DIR, CSV_OUT_DIR): d.mkdir(parents=True, exist_ok=True)


# --------------- Global Variables --------------- #

# Total number of people
PEOPLE_GLOBAL = 10000 

# Default vehicle types and edge IDs
PRIVATE_VTYPE = "car"   

# TODO: Still undefined, haven't created flows for this yet
PUBLIC_VTYPE = "bus"     

# Simulation runtime per "day" (seconds) 
SIM_RUNTIME = 24 * 3600  # 24h in seconds 



POLICY_NAME = "baseline"

if __name__ == "__main__":
    # TODO: replace edges with actual values after manually creating in netedit
    sumo_flows = {
    "private_flows": [
        # Private vehicle flow: cars using route "r_upper"
        # ["A4B4", "B4C4", "C4D4", "D4E4", "E4E3" ,"E3E2" ,"E2D2"] might not work as list

        # Percentages here are used to define the percentage of total people attributed to
        # each specific flow (in this case, private cars)
        ("flow_0", "A2A3 A3B3 B3C2 C2D2 D2E2 E2J1", 0, SIM_RUNTIME, 1.0),  # 100% of private flow
    ],
    "public_flows": [
        # Public transport flow: buses using route "bus"
        # In this case, it also assigns a percentage of people to each flow of buses
        # However, that number is divided by 80 to accomodate and create new buses
        # TODO: Buses always run, even if empty. Cars created must ALWAYS be the same.
        # The percentage is only important to understande whether we can allocate more
        # people to buses or if they're all full. 
        # Add a stops list (busStop id, dwell time seconds) to make buses halt at the defined stops
        ("flow_1", "A2A1 A1B1 B1C2 C2D2 D2E2 E2J1", 0, SIM_RUNTIME, 1.0,
         [("bs_0", 15), ("bs_1", 15), ("bs_2", 15), ("bs_3", 15)]),  # 100% of public flow
    ],
}

    # Example policy: logistic adoption reaching 80% after a few days
    my_policy = {"id": "policy_bus_subsidy", "type": "logistic", "L": 0.8, "k": 0.8, "x0": 3}

    runSim(
        n_simulations=1,
        days_per_sim=7,
        policy=my_policy,
        num_agents_global=PEOPLE_GLOBAL,
        flows_template=sumo_flows,
        flows_dir=FLOWS_DIR,
        raw_out_dir=RAW_OUT_DIR,
        csv_out_dir=CSV_OUT_DIR,
        sumo_net_file=SUMO_NET_FILE,
        sumo_binary=SUMO_BINARY,
        additional_files=ADDITIONAL_FILES,
        private_vtype=PRIVATE_VTYPE,
        public_vtype=PUBLIC_VTYPE,
    )
    
    delete = str(input("Do you wish to delete the simulation csv results? (y/n)"))
    
    csvCleaner(delete, csv_out_dir=CSV_OUT_DIR)

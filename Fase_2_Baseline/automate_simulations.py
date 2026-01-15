import os
import json
from pathlib import Path
from automate_utils import runSim, csvCleaner, resolve_sumo_binary, summarize_daily_kpis

"""
The goal of this code is to automate the somulations. It allows to:
    Change between maps with variables:
        - 
        -
        -
    Change the number of people in the simulation with the variable: PEOPLE_GLOBAL
    Saves the results in the PO
"""

# VARIABLES TO CHANGE/ADAPT
MAP_TYPE = ["grid"]
POLICY_TYPE = ["UserPreference_Baseline", "UserPreference_Time", "UserPreference_Cost", "UserPreference_CO2"]
PEOPLE_GLOBAL = [25000]
# if run inside VS Code add to CSV_CLEANER_FOLDER and OUT_DIR "Fase_0", so it would be like "Fase_0\_clean_csvs_"
CSV_CLEAN_FOLDER = Path("_clean_csvs_")
OUT_DIR = Path("_sumo_runs_")

# Baseline flows:
BUSSTOP_DEFS_BASELINE = {
    "BS_L1_0": {"lane": "A1B1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L1_1": {"lane": "F2G1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L1_2": {"lane": "H1I1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L2_0": {"lane": "A1B1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L2_1": {"lane": "D1E0_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L2_2": {"lane": "H1I1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
}

# Grid Flows
BUSSTOP_DEFS_GRID = {
    "BS_L1_0": {"lane": "A2B2_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L1_1": {"lane": "C2D2_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L1_2": {"lane": "D2E2_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},

    "BS_L2_0": {"lane": "C0C1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L2_1": {"lane": "C2C3_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L2_2": {"lane": "C3C4_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},

    "BS_L3_0": {"lane": "A0B0_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L3_1": {"lane": "E0E1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L3_2": {"lane": "E4D4_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    "BS_L3_3": {"lane": "A4A3_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
}

# Private routes with rush windows (car) - BASELINE
FLOWS_TEMPLATES_BASELINE = {
    "private_flows": [
    # Cada tuplo: (flow_id, route_edges_or_distribution, start, end, percentage)
    # Aqui, route_edges_or_distribution é uma LISTA de (edges, prob) -> cria <routeDistribution>
    (
        "flow_0",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.5),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.5),
        ],
        0, 6*3600, 0.10
    ),
    (
        "flow_1",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.5),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.5),
        ],
        6*3600, 9*3600, 0.50
    ),
    (
        "flow_2",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.5),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.5),
        ],
        9*3600, 16*3600, 0.30
    ),
    (
        "flow_3",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.5),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.5),
        ],
        16*3600, 24*3600, 0.10
    ),

    ]
}

# Private routes with rush windows (car) - GRID
FLOWS_TEMPLATES_GRID = {
    "private_flows": [
    # Cada tuplo: (flow_id, route_edges_or_distribution, start, end, percentage)
    # Aqui, route_edges_or_distribution é uma LISTA de (edges, prob) -> cria <routeDistribution>
    (
        "flow_0",
        [
            ("A2B2 B2C2 C2D2 D2E2", 0.25),
            ("C0C1 C1C2 C2C3 C3B3 B3A3",0.25),
            ("A0A1 A1B1 B1B2 B2C2 C2D2 D2D3 D3D4",0.25),
            ("C4B4 B4A4 A4A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
        ],
        0, 6*3600, 0.10
    ),
    (
        "flow_1",
        [
            ("A2B2 B2C2 C2D2 D2E2", 0.25),
            ("C0C1 C1C2 C2C3 C3B3 B3A3",0.25),
            ("A0A1 A1B1 B1B2 B2C2 C2D2 D2D3 D3D4",0.25),
            ("C4B4 B4A4 A4A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
        ],
        6*3600, 9*3600, 0.50
    ),
    (
        "flow_2",
        [
            ("A2B2 B2C2 C2D2 D2E2", 0.25),
            ("C0C1 C1C2 C2C3 C3B3 B3A3",0.25),
            ("A0A1 A1B1 B1B2 B2C2 C2D2 D2D3 D3D4",0.25),
            ("C4B4 B4A4 A4A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
        ],
        9*3600, 16*3600, 0.30
    ),
    (
        "flow_3",
        [
            ("A2B2 B2C2 C2D2 D2E2", 0.25),
            ("C0C1 C1C2 C2C3 C3B3 B3A3",0.25),
            ("A0A1 A1B1 B1B2 B2C2 C2D2 D2D3 D3D4",0.25),
            ("C4B4 B4A4 A4A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
        ],
        16*3600, 24*3600, 0.10
    ),

    ]
}


# --- Padrões PT (spawn no from_stop e ride até to_stop)
CIVILLIAN_RIDES_BASELINE = [
    {"from_stop": "BS_L1_0", "to_stop": "BS_L1_1", "line": "L1"},
    {"from_stop": "BS_L1_0", "to_stop": "BS_L1_2", "line": "L1"},
    {"from_stop": "BS_L2_0", "to_stop": "BS_L2_1", "line": "L2"},
    {"from_stop": "BS_L2_0", "to_stop": "BS_L2_2", "line": "L2"},
]


CIVILLIAN_RIDES_GRID = [
    {"from_stop": "BS_L1_0", "to_stop": "BS_L1_1", "line": "L1"},
    {"from_stop": "BS_L1_1", "to_stop": "BS_L1_2", "line": "L1"},
    {"from_stop": "BS_L2_0", "to_stop": "BS_L2_1", "line": "L2"},
    {"from_stop": "BS_L2_1", "to_stop": "BS_L2_2", "line": "L2"},
    {"from_stop": "BS_L3_0", "to_stop": "BS_L3_1", "line": "L3"},
    {"from_stop": "BS_L3_1", "to_stop": "BS_L3_2", "line": "L3"},
    {"from_stop": "BS_L3_2", "to_stop": "BS_L3_3", "line": "L3"},
]

for i in range(len(MAP_TYPE)):
    for j in range(len(PEOPLE_GLOBAL)):
        for k in range(len(POLICY_TYPE)):

            BASE = Path(__file__).resolve().parent
            # Variable that has the name of the folder that has the results. Something like baseline_1000 or grid_25000
            POLICY_NAME_FOLDER = f"{MAP_TYPE[i]}_{POLICY_TYPE[k]}_{PEOPLE_GLOBAL[j]}"
            # Name of the folder that has the maps to use (folder with net, routes, etc)
            SCENARIO_FOLDER = f"{MAP_TYPE[i]}_map"
            SUMO_NET_FILE = (BASE / SCENARIO_FOLDER / "map.net.xml").resolve()
            BUS_ROUTES = (BASE / SCENARIO_FOLDER / "bus_routes.rou.xml").resolve()
            BUS_STOPS = (BASE / SCENARIO_FOLDER / "bus_stops.add.xml").resolve()

            OUT_DIR.mkdir(parents=True, exist_ok=True)

            SUMO_BINARY = resolve_sumo_binary()
            #SUMO_BINARY = "sumo-gui"

            # --------------- Directories Setup --------------- #
            AGGREGATED_CSV = OUT_DIR / "aggregated_tripinfo_emissions.csv"
            SUMMARY_CSV = OUT_DIR / "summary_per_run.csv"
            OUT_DIR.mkdir(parents=True, exist_ok=True)

            # --------------------- POLICIES
            up_baseline = {"id": POLICY_NAME_FOLDER, "type": "utility", "base": 0.30,  "learning_rate": 0.20,        # inércia (0..1)
            "weights": {"time": -0.002, "cost": -0.30, "pollution": -0.000000001}, "car_cost_per_km": 0.40, "bus_fare": 0.10}

            up_time = {"id": POLICY_NAME_FOLDER, "type": "utility", "base": 0.30,  "learning_rate": 0.20,        # inércia (0..1)
            "weights": {"time": -0.001, "cost": -0.30, "pollution": -0.000000001}, "car_cost_per_km": 0.40, "bus_fare": 0.10}

            up_cost = {"id": POLICY_NAME_FOLDER, "type": "utility", "base": 0.30,  "learning_rate": 0.20,        # inércia (0..1)
            "weights": {"time": -0.002, "cost": -1.00, "pollution": -0.000000001}, "car_cost_per_km": 0.40, "bus_fare": 0.10}

            up_co2 = {"id": POLICY_NAME_FOLDER, "type": "utility", "base": 0.30,  "learning_rate": 0.20,        # inércia (0..1)
            "weights": {"time": -0.002, "cost": -0.30, "pollution": -0.0000001}, "car_cost_per_km": 0.40, "bus_fare": 0.10}

            if POLICY_TYPE[k] == "UserPreference_Time":
                MY_POLICY = up_time
            elif POLICY_TYPE[k] == "UserPreference_Cost":
                MY_POLICY = up_cost
            elif POLICY_TYPE[k] == "UserPreference_CO2":
                MY_POLICY = up_co2
            else:
                MY_POLICY = up_baseline

            # --------------------- SIMULATION CONFIGURATIONS
            people = PEOPLE_GLOBAL[j]
            SIM_RUNTIME = 24 * 3600
            NUMBER_SIMULATIONS = 1
            NUMBER_OF_DAYS_PER_SIMULATION = 14
            PUBLIC_PERCENTAGE = 0.3     # percentagem de pessoas que começam no transporte público
            PRIVATE_VTYPE = "car"   
            PUBLIC_VTYPE = "bus" 

            # --------------------- RESULTS OUTPUTS
            RESULTS_DIR = OUT_DIR / POLICY_NAME_FOLDER
            FLOWS_DIR = RESULTS_DIR / "flows"
            RAW_XML = RESULTS_DIR / "raw_xml"
            RAW_CSV = RESULTS_DIR / "raw_csv"

            for d in (RESULTS_DIR, FLOWS_DIR, RAW_XML, RAW_CSV): d.mkdir(parents=True, exist_ok=True)    

            # --------------- Map Configurations ---------------
            if MAP_TYPE[i] == "baseline":
                bus_stops = BUSSTOP_DEFS_BASELINE
                flows = FLOWS_TEMPLATES_BASELINE
                civillian_flows = CIVILLIAN_RIDES_BASELINE
            else:
                bus_stops = BUSSTOP_DEFS_GRID
                flows = FLOWS_TEMPLATES_GRID
                civillian_flows = CIVILLIAN_RIDES_GRID


            # --- PT rush windows (percentagens do total diário de PESSOAS PT -> somar 1.0)
            RUSH_WINDOW_PUBLIC = [
                (0, 6*3600, 0.20),
                (6*3600, 20*3600, 0.70),
                (20*3600, 24*3600, 0.10),
            ]


            if __name__ == "__main__":

                print("\n\n==========================================")
                print("NEW SIMULATION - CHARACTERISTICS:")
                print(f"- Type of Map: {MAP_TYPE[i]}")
                print(f"- Number of People: {PEOPLE_GLOBAL[j]}")
                print(f"- Policy Type: {POLICY_TYPE[k]}")
                print(f"- Number of simultions: {NUMBER_SIMULATIONS}")
                print(f"- Number of days per simulation: {NUMBER_OF_DAYS_PER_SIMULATION}")
                print(f"- Policy: {MY_POLICY}")


                runSim(
                    n_simulations=NUMBER_SIMULATIONS,
                    days_per_sim=NUMBER_OF_DAYS_PER_SIMULATION,
                    policy=MY_POLICY,
                    num_agents_global=people,
                    flows_template=flows,
                    rush_windows_public=RUSH_WINDOW_PUBLIC,
                    civillian_rides=civillian_flows,
                    busstop_defs=bus_stops,
                    static_route_files=[BUS_ROUTES],
                    flows_dir=FLOWS_DIR,
                    raw_out_dir=RAW_XML,
                    csv_out_dir=RAW_CSV,
                    sumo_net_file=SUMO_NET_FILE,
                    sumo_binary=SUMO_BINARY,
                    additional_files=[BUS_STOPS],
                    additional_sumo_args=["--begin", "0", "--end", str(SIM_RUNTIME)],
                    private_vtype=PRIVATE_VTYPE,
                    public_vtype=PUBLIC_VTYPE,
                )
                
                print("ok1")
                df_clean = csvCleaner(policy_folder=RAW_CSV, policy_name=POLICY_NAME_FOLDER, clean=CSV_CLEAN_FOLDER)
                print("ok2")
                summary = summarize_daily_kpis(df_clean, policy_id=POLICY_NAME_FOLDER)
                summary_path = (RESULTS_DIR / "summary_daily_kpis.csv").resolve()
                summary.to_csv(summary_path, index=False)
                print(f"Saved KPI summary: {summary_path}")
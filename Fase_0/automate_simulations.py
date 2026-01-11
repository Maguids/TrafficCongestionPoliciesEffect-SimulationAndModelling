import os
import json
from pathlib import Path
from automate_utils import runSim, csvCleaner, resolve_sumo_binary, summarize_daily_kpis

BASE = Path(__file__).resolve().parent
POLICY_NAME_FOLDER = "baseline_map_2" # Nome que as pastas vão ter e nome onde estão as coisas da policy
SCENARIO_FOLDER = "baseline_map" #nOME ONDE ESTÃO OS MAPAS 
SUMO_NET_FILE = (BASE / SCENARIO_FOLDER / "baseline.net.xml").resolve()
BUS_ROUTES = (BASE / SCENARIO_FOLDER / "bus_routes.rou.xml").resolve()
BUS_STOPS = (BASE / SCENARIO_FOLDER / "bus_stops.add.xml").resolve()

OUT_DIR = Path("sumo_runs")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUMO_BINARY = resolve_sumo_binary()
#SUMO_BINARY = "sumo-gui"

# --------------- Directories Setup --------------- #
AGGREGATED_CSV = OUT_DIR / "aggregated_tripinfo_emissions.csv"
SUMMARY_CSV = OUT_DIR / "summary_per_run.csv"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# --------------------- POLICIES
logistic_policy = {"id": POLICY_NAME_FOLDER, "type": "logistic", "L": 0.9, "k": 0.3, "x0": 3}
utility_policy = {"id": POLICY_NAME_FOLDER, "type": "utility","base": 0.30,  "learning_rate": 0.35,        # inércia (0..1)
"weights": {"time": -0.002, "cost": -0.30, "pollution": -0.000001}, "car_cost_per_km": 0.20, "bus_fare": 1.50}
discrete_policy = {"id": POLICY_NAME_FOLDER, "type": "None", "base": 0.3}

# --------------------- SIMULATION CONFIGURATIONS
PEOPLE_GLOBAL = 100
SIM_RUNTIME = 24 * 3600
NUMBER_SIMULATIONS = 1
NUMBER_OF_DAYS_PER_SIMULATION = 14
MY_POLICY = logistic_policy
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

# Bus stops
BUSSTOP_DEFS = {
        "BS_L1_0": {"lane": "A1B1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L1_1": {"lane": "F2G1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L1_2": {"lane": "H1I1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L2_0": {"lane": "A1B1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L2_1": {"lane": "D1E0_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L2_2": {"lane": "H1I1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    }

# Private routes with rush windows (car)
FLOWS_TEMPLATES = {
    "private_flows": [
    # Cada tuplo: (flow_id, route_edges_or_distribution, start, end, percentage)
    # Aqui, route_edges_or_distribution é uma LISTA de (edges, prob) -> cria <routeDistribution>
    (
        "flow_0",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.3),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.7),
        ],
        0, 6*3600, 0.10
    ),
    (
        "flow_1",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.4),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.6),
        ],
        6*3600, 9*3600, 0.50
    ),
    (
        "flow_2",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.2),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.8),
        ],
        9*3600, 16*3600, 0.30
    ),
    (
        "flow_3",
        [
            ("A1B1 B1C1 C1D1 D1E0 E0F0 F0G1 G1H1 H1I1 I1J1", 0.25),
            ("A1B1 B1C1 C1D1 D1E2 E2F2 F2G1 G1H1 H1I1 I1J1", 0.75),
        ],
        16*3600, 24*3600, 0.10
    ),

    ]
}

# --- PT rush windows (percentagens do total diário de PESSOAS PT -> somar 1.0)
RUSH_WINDOW_PUBLIC = [
    (0, 6*3600, 0.20),
    (6*3600, 20*3600, 0.70),
    (20*3600, 24*3600, 0.10),
]

# --- Padrões PT (spawn no from_stop e ride até to_stop)
CIVILLIAN_RIDES = [
    {"from_stop": "BS_L1_0", "to_stop": "BS_L1_1", "line": "L1"},
    {"from_stop": "BS_L1_0", "to_stop": "BS_L1_2", "line": "L1"},
    {"from_stop": "BS_L2_0", "to_stop": "BS_L2_1", "line": "L2"},
    {"from_stop": "BS_L2_0", "to_stop": "BS_L2_2", "line": "L2"},
]


if __name__ == "__main__":


    runSim(
        n_simulations=NUMBER_SIMULATIONS,
        days_per_sim=NUMBER_OF_DAYS_PER_SIMULATION,
        policy=MY_POLICY,
        num_agents_global=PEOPLE_GLOBAL,
        flows_template=FLOWS_TEMPLATES,
        rush_windows_public=RUSH_WINDOW_PUBLIC,
        civillian_rides=CIVILLIAN_RIDES,
        busstop_defs=BUSSTOP_DEFS,
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
    df_clean = csvCleaner(policy_folder=RAW_CSV, policy_name=POLICY_NAME_FOLDER)
    print("ok2")
    summary = summarize_daily_kpis(df_clean, policy_id=POLICY_NAME_FOLDER)
    summary_path = (RESULTS_DIR / "summary_daily_kpis.csv").resolve()
    summary.to_csv(summary_path, index=False)
    print(f"Saved KPI summary: {summary_path}")

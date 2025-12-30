import subprocess
import uuid
import os
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List
import pandas as pd 
import os
import re
from send2trash import send2trash



XML2CSV_PATH = Path("/opt/homebrew/opt/sumo/share/sumo/tools/xml/xml2csv.py")
# XML2CSV_PATH = Path(r"D:\Rafa\SUMO\tools\xml\xml2csv.py")

                  
# ----------------------------
#     Flow file generator
# ----------------------------

# All flows need to be defined according to the example in the main file
def add_flow(fid, route_edges, start, end, percentage, num_agents, vtype, root):
    """
    Add a single route and flow to the XML tree.
    """
    # Create route entry
    route_id = f"r_{fid}"
    ET.SubElement(root, "route", attrib={"id": route_id, "edges": route_edges})

    # Compute number of vehicles for this flow
    n_vehicles = int(round(num_agents * percentage))
    if n_vehicles <= 0:
        return

    # Calculate flow frequency (vehicles per period)
    period = max(1, (end - start) / n_vehicles)

    ET.SubElement(
        root,
        "flow",
        attrib={
            "id": fid,
            "type": vtype,
            "begin": str(start),
            "end": str(end),
            "period": f"{period:.2f}",
            "route": route_id,
        },
    )

def createFlowFile(out_path, num_agents, acceptance_rate_public, flows_template,
                  private_vtype="car", public_vtype="bus"):
    """
    Generate a SUMO-compatible routes file with <vType>, <route>, and <flow>.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Total number of people is split between private and public 
    num_public = int(round(num_agents * acceptance_rate_public))
    num_private = max(0, num_agents - num_public)

    # Root element
    root = ET.Element(
        "routes",
        attrib={
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://sumo.dlr.de/xsd/routes_file.xsd",
        },
    )
    
    ET.SubElement(
        root,
        "vType",
        attrib={
            "id": "car",
            "length": "4.50",
            "minGap": "2.50",
            "maxSpeed": "13.90",
            "emissionClass": "HBEFA3/PC_G_EU6",
            "guiShape": "passenger",
            "color": "red",
            "accel": "2.6",
            "decel": "4.5",
            "sigma": "0.5",
        },
    )
    ET.SubElement(
        root,
        "vType",
        attrib={
            "id": "bus",
            "length": "10",
            "minGap": "2.50",
            "maxSpeed": "10",
            "emissionClass": "HBEFA3/PC_G_EU6",
            "guiShape": "bus",
            "color": "blue",
            "accel": "2.6",
            "decel": "4.5",
            "sigma": "0.5",
        },
    )

    # Add private flows
    for flow in flows_template["private_flows"]:
        fid, route_edges, start, end, percentage = flow
        add_flow(fid, route_edges, start, end, percentage, num_private, private_vtype, root)

    
    num_public = num_agents/80 # each bus can hold 80 people
    
    # Add public flows (optional stops at bus stops)
    for flow in flows_template["public_flows"]:
        # Allow an optional stops list as a 6th element: [(busStopId, duration), ...]

        fid, route_edges, start, end, percentage, stops = flow

        # create flow and attach stop children if any
        add_flow(fid, route_edges, start, end, percentage, num_public, public_vtype, root)

        if stops:
            # find the flow element we just added (last one)
            last_flow = root.findall("flow")[-1]
            for stop_id, stop_duration in stops:
                ET.SubElement(
                    last_flow,
                    "stop",
                    attrib={
                        "busStop": stop_id,
                        "duration": str(stop_duration),
                    },
                )

    # Write to disk
    tree = ET.ElementTree(root)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)

    print(f"Flow file written: {os.path.abspath(out_path)}")
    return out_path


# ----------------------------
#        Running SUMO
# ----------------------------
def runSUMO(flowfile, netfile, tripinfo_out,
                  emissions_out, sumo_binary="sumo", additional_files=None, additional_sumo_args=None):
    """
    Calls SUMO in batch mode, using a flowfile. Produces tripinfo and emissions xml outputs.
    Returns (returncode, stdout, stderr).
    """
    args = [
        sumo_binary,
        "-n", netfile,
        "-r", str(flowfile),  # flow file
        "--tripinfo-output", str(tripinfo_out),
        "--emission-output", str(emissions_out),
        "--duration-log.statistics",
        "--no-warnings",
        # we can define --seed here for reproducibility
    ]
    if additional_files:
        # SUMO accepts a comma-separated list for multiple additional files
        add_arg = ",".join(str(f) for f in additional_files)
        args += ["--additional-files", add_arg]
    if additional_sumo_args: args += additional_sumo_args
    
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr

# ----------------------------
# Preference/acceptance functions (standard)
# ----------------------------
def linear_acceptance(base, slope, day):
    """Simple linear evolution: acceptance = base + slope * day (clamped 0..1)"""
    val = base + slope * day
    return max(0.0, min(1.0, val))

def logistic_acceptance(L, k, x0, day):
    """Logistic curve for adoption: L / (1 + exp(-k*(day-x0)))"""
    return L / (1.0 + math.exp(-k * (day - x0)))

def utility_preference(time_private, time_public, cost_private, cost_public, 
                       pollution_private, pollution_public, weights):
    """
    Compute probability of choosing public transport using a Multinomial Logit (softmax) over utilities.
    Returns probability in [0,1].
    weights: e.g. {'time': -1.0, 'cost': -0.5, 'pollution': -0.2}
    """
    # utility = w_time * time + w_cost * cost + w_pollution * pollution
    u_private = weights.get("time", 0.0) * time_private + weights.get("cost", 0.0) * cost_private + weights.get("pollution", 0.0) * pollution_private
    u_public = weights.get("time", 0.0) * time_public + weights.get("cost", 0.0) * cost_public + weights.get("pollution", 0.0) * pollution_public

    # Avoid overflow
    maxu = max(u_private, u_public)
    exp_priv = math.exp(u_private - maxu)
    exp_pub = math.exp(u_public - maxu)
    p_public = exp_pub / (exp_priv + exp_pub)
    return p_public

# ----------------------------
# Example policy update function
# ----------------------------
def updatePolicy(policy, day):
    """
    Example: policy contains a base acceptance and a daily growth rate or curve parameters.
    Return acceptance_rate_public for given day.
    """
    if policy.get("type") == "linear":
        return linear_acceptance(policy.get("base", 0.1), policy.get("slope", 0.02), day)
    elif policy.get("type") == "logistic":
        return logistic_acceptance(policy.get("L", 0.9), policy.get("k", 0.3), policy.get("x0", 3), day)
    else:
        # default constant acceptance
        return policy.get("base", 0.1)

# ----------------------------
# Main Function
# ----------------------------

def runSim(n_simulations=3, days_per_sim=7, policy=None,
           num_agents_global=200, flows_template=None,
           flows_dir=Path("sumo_runs/flows"),
           raw_out_dir=Path("sumo_runs/raw_xml"),
           csv_out_dir=Path("sumo_runs/raw_csv"),
           sumo_net_file=Path("automate_flow/core/manhattan.net.xml"),
           sumo_binary="sumo",
           additional_files=None,
           private_vtype="car",
           public_vtype="bus",
           xml2csv_path=XML2CSV_PATH):
    """
        I'll be using this one until I can guarantee that all xmls are correctly created.
    """
    if policy is None:
        # default policy
        policy = {"id": "policy_default", "type": "linear", "base": 0.05, "slope": 0.05}

    for sim_id in range(1, n_simulations + 1):
        print(f"Starting simulation {sim_id}/{n_simulations} (policy={policy.get('id')})")

        for day in range(1, days_per_sim + 1):
            acceptance = updatePolicy(policy, day - 1)
            print(f"  Simulation {sim_id} Day {day}: acceptance_rate_public = {acceptance:.3f}")

            num_agents = num_agents_global

            # Generate a flows xml for this day
            flowfile = flows_dir / f"flows_sim{sim_id}_day{day}_{policy.get('id')}.xml"
            createFlowFile(flowfile, num_agents, acceptance, flows_template,
                           private_vtype=private_vtype, public_vtype=public_vtype)

            # Output filenames
            tripinfo_out = raw_out_dir / f"tripinfo_sim{sim_id}_day{day}_{policy.get('id')}.xml"
            emissions_out = raw_out_dir / f"emissions_sim{sim_id}_day{day}_{policy.get('id')}.xml"

            # Run SUMO once for this day
            ret, out, err = runSUMO(flowfile, sumo_net_file, tripinfo_out, emissions_out,
                                    sumo_binary=sumo_binary,
                                    additional_files=additional_files)
            if ret != 0: print(f"SUMO returned non-zero code {ret}. stderr:\n{err}")
            else: print(f"Simulation{sim_id}, day {day}: DONE.")

            '''
            # Emissions .xml -> .csv pipeline
            emissions_csv_tool_out = CSV_OUT_DIR / f"emissions_sim{sim_id}_day{day}_{policy.get('id')}.csv"
            if emissions_out.exists():
                cmd = ["python", str(XML2CSV_PATH), str(emissions_out), "--output", str(emissions_csv_tool_out)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0: print(f"Emissions CSV converted: {emissions_csv_tool_out}")
                else: print(f"CONVERSION FAILED:\n{result.stderr}")
            else: print(f"EMISSIONS XML NOT FOUND: {emissions_out}")
            '''

            # Tripinfo .xml -> .csv pipeline
            tripinfo_csv_tool_out = csv_out_dir / f"tripinfo_sim{sim_id}_day{day}_{policy.get('id')}.csv"
            if tripinfo_out.exists():
                cmd = ["python", str(xml2csv_path), str(tripinfo_out), "--output", str(tripinfo_csv_tool_out)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0: print(f"tripinfo CSV converted: {tripinfo_csv_tool_out}")
                else: print(f"CONVERSION FAILED:\n{result.stderr}")
            else: print(f"tripinfo XML NOT FOUND: {tripinfo_out}")


    print("All simulations completed.")
    print(f"Individual CSVs saved to: {csv_out_dir}")

# -------------------------------
# Cleaning and Preprocssing csvs
# -------------------------------


def orderSpawn(df):
    # Extract flow number and car number
    df["flow_id"] = df["tripinfo_id"].str.extract(r"flow_(\d+)\.\d+").astype(int)
    df["car_num"] = df["tripinfo_id"].str.split(".", n=1).str[1].astype(int)

    # Sort by flow_id first, then by car_num
    df = df.sort_values(by=["flow_id", "car_num"], ascending=[True, True]).drop(columns=["car_num"])

    return df

def getClean(f):
    
    '''
        New Dataframe:
        - tripinfo_id : str
        - tripinfo_vType : str
        - day         : int
        - sim         : int
        - CO2_abs     : float
        - departDelay : float
        - waitingTime : float
        - waitingCount: int
        - timeLoss    : float
    '''
    
    # Read file
    df = pd.read_csv(f, sep=";")

    # Get day and simulation from file name
    match = re.search(r"sim(\d+)_day(\d+)", f)
    if match:
        sim = int(match.group(1))
        day = int(match.group(2))

    # Order: flow -> car
    df = orderSpawn(df)

    # Start clean dataframe (some column names are simplified)
    df_clean = pd.DataFrame()

    # Increasing unique ID
    df_clean["tripinfo_id"] = df["tripinfo_id"]
    df_clean["tripinfo_vType"] = df["tripinfo_vType"]

    # Increasing day and simulation
    df_clean["day"] = day
    df_clean["sim"] = sim 

    # Total daily CO2 emission in mg per car
    df_clean["CO2_abs"] = df["emissions_CO2_abs"]

    # Total daily departure delays, waiting times,
    # waiting counts and time losses
    df_clean["departDelay"] = df["tripinfo_departDelay"]
    df_clean["waitingTime"] = df["tripinfo_waitingTime"]
    df_clean["waitingCount"] = df["tripinfo_waitingCount"]
    df_clean["timeLoss"] = df["tripinfo_timeLoss"]

    return df_clean   


def csvCleaner(delete, policy_folder, policy_name, csv_out_dir=Path("sumo_runs/raw_csv")):

    # Gets every file name in policy_folder in order
    filenames = sorted(
    (policy_folder + f) for f in os.listdir(policy_folder)
    if os.path.isfile(os.path.join(policy_folder, f))
    )

    # Initializes the global dataframe
    df = getClean(filenames[0])
    df_global = df.copy()

    # Iteratively applies every other csv and concatenates to the bottom of the previous 
    for f in filenames[1:]: df_global = pd.concat([df_global, getClean(f)], ignore_index=True)
    
    df_global.to_csv("clean_csvs/" + policy_name + ".csv", index=False)

    if delete == "y":
        # sends all csvs to recycle bin (accidental delete protection)
        for p in Path(csv_out_dir).iterdir():
            if p.is_file(): send2trash(str(p))

    return df_global

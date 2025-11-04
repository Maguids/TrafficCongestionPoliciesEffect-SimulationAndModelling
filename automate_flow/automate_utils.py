import subprocess
import uuid
import os
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List
import pandas as pd 
from automate_simulations import PRIVATE_VTYPE, PUBLIC_VTYPE, SUMO_BINARY
from automate_simulations import PEOPLE_GLOBAL, FLOWS_DIR, RAW_OUT_DIR
from automate_simulations import SUMO_NET_FILE, OUT_DIR, RAW_OUT_DIR, SIM_RUNTIME

# CSV converter!
XML2CSV_PATH = Path(r"D:\Rafa\SUMO\tools\xml\xml2csv.py")

                  
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

def createFlowFile(out_path, num_agents, acceptance_rate_public, flows_template):
    """
    Generate a SUMO-compatible routes file with <vType>, <route>, and <flow>.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

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

    # Add vehicle types
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
            "length": "7.50",
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
        add_flow(fid, route_edges, start, end, percentage, num_private, PRIVATE_VTYPE, root)

    # Add public flows
    for flow in flows_template["public_flows"]:
        fid, route_edges, start, end, percentage = flow
        add_flow(fid, route_edges, start, end, percentage, num_public, PUBLIC_VTYPE, root)

    # Write to disk
    tree = ET.ElementTree(root)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)

    print(f"✅ Flow file written: {os.path.abspath(out_path)}")
    return out_path


# ----------------------------
#        Running SUMO
# ----------------------------
def runSUMO(flowfile, netfile, tripinfo_out,
                  emissions_out, additional_sumo_args):
    """
    Calls SUMO in batch mode, using a flowfile. Produces tripinfo and emissions xml outputs.
    Returns (returncode, stdout, stderr).
    """
    args = [
        SUMO_BINARY,
        "-n", netfile,
        "-r", str(flowfile),  # flow file
        "--tripinfo-output", str(tripinfo_out),
        "--emission-output", str(emissions_out),
        "--duration-log.statistics",
        "--no-warnings",
        # we can define --seed here for reproducibility
    ]
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
           num_agents_global=PEOPLE_GLOBAL, flows_template=None):
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
            flowfile = FLOWS_DIR / f"flows_sim{sim_id}_day{day}_{policy.get('id')}.xml"
            createFlowFile(flowfile, num_agents, acceptance, flows_template)

            # Output filenames
            tripinfo_out = RAW_OUT_DIR / f"tripinfo_sim{sim_id}_day{day}_{policy.get('id')}.xml"
            emissions_out = RAW_OUT_DIR / f"emissions_sim{sim_id}_day{day}_{policy.get('id')}.xml"

            # Run SUMO once for this day
            ret, out, err = runSUMO(flowfile, SUMO_NET_FILE, tripinfo_out, emissions_out)
            if ret != 0: print(f"SUMO returned non-zero code {ret}. stderr:\n{err}")
            else:
                print(f"Simulation{sim_id}, day {day}: DONE.")

            # TODO: make this general use
            emissions_csv_tool_out = OUT_DIR / f"emissions_tool_sim{sim_id}_day{day}_{policy.get('id')}.csv"
            if emissions_out.exists():
                cmd = ["python", str(XML2CSV_PATH), str(emissions_out), "--output", str(emissions_csv_tool_out)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0: print(f"Emissions CSV converted: {emissions_csv_tool_out}")
                else: print(f"CONVERSION FAILED:\n{result.stderr}")
            else: print(f"EMISSIONS XML NOT FOUND: {emissions_out}")


    print("All simulations completed.")
    print(f"Individual CSVs saved to: {OUT_DIR}")
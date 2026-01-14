from __future__ import annotations

import math
import os
import re 
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

import pandas as pd 
import xml.etree.ElementTree as ET
import random

# -----------------------------------------------------------------------------
# ---------------------------- SUMO Path resolvers ----------------------------
# -------------------------- Adapts for Windows e MAC -------------------------
# -----------------------------------------------------------------------------

"""
Resolve SUMO_HOME if set.
"""
def resolve_sumo_home() -> Optional[Path]:
    env = os.environ.get("SUMO_HOME")
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p
    return None

"""
    Resolves SUMO binary on a cross-platform manner
    Order:
        1) preferres (if exists / os on PATH)
        2) SUMO_BINARY env
        3) SUMO_HOME/bin/(sumo|sumo.exe|sumo-gui|sumo-gui.exe)
        4) PATH (shutil.which)
"""
def resolve_sumo_binary(preferred: Optional[str] = None) -> str:
    # 1) preferred arg
    candidates: List[str] = []
    if preferred:
        candidates.append(preferred)

    # 2) env SUMO_BINARY
    env_bin = os.environ.get("SUMO_BINARY")
    if env_bin and env_bin not in candidates:
        candidates.append(env_bin)

    # 3) SUMO_HOME
    sumo_home = resolve_sumo_home()
    if sumo_home:
        bin_dir = sumo_home / "bin"
        # tenta sumo e sumo-gui
        for name in ("sumo", "sumo-gui"):
            exe = name + (".exe" if os.name == "nt" else "")
            candidates.append(str(bin_dir / exe))

    # 4) PATH fallbacks
    candidates.extend(["sumo", "sumo-gui"])

    for c in candidates:
        p = Path(c)
        # caminho explícito
        if p.exists():
            return str(p)
        # comando no PATH
        w = shutil.which(c)
        if w:
            return w

    raise FileNotFoundError(
        "Unable to find SUMO' binary."
        "Install SUMO and/or define SUMO_HOME (recommended) or SUMO_BINARY"
    )


# -----------------------------------------------------------------------------


"""
    Resolves tools/xml/xml2csv.py (cross-platform).
    Searches in:
      - explicit
      - SUMO_HOME/tools/xml/xml2csv.py
      - SUMO_HOME/share/sumo/tools/xml/xml2csv.py (Homebrew-like)
      - (bin do sumo)/../tools/xml/xml2csv.py
      - some commun paths
"""
def resolve_xml2csv_path(explicit: Optional[Path] = None, sumo_binary: Optional[str] = None) -> Path:
    if explicit:
        explicit = Path(explicit).expanduser().resolve()
        if explicit.exists():
            return explicit

    candidates: List[Path] = []
    sumo_home = resolve_sumo_home()

    if sumo_home:
        candidates += [
            sumo_home / "tools" / "xml" / "xml2csv.py",
            sumo_home / "share" / "sumo" / "tools" / "xml" / "xml2csv.py",
        ]

    if sumo_binary:
        sb = Path(sumo_binary)
        # If it is a path .../bin/sumo(.exe)
        if sb.exists():
            base = sb.parent.parent  # .../bin/ -> ...
            candidates += [
                base / "tools" / "xml" / "xml2csv.py",
                base / "share" / "sumo" / "tools" / "xml" / "xml2csv.py",
            ]

    # common path (macOS brew / linux / windows installs típicos)
    candidates += [
        Path("/opt/homebrew/opt/sumo/share/sumo/tools/xml/xml2csv.py"),
        Path("/usr/local/opt/sumo/share/sumo/tools/xml/xml2csv.py"),
        Path("/usr/share/sumo/tools/xml/xml2csv.py"),
        Path("C:/Program Files/Eclipse/Sumo/tools/xml/xml2csv.py"),
        Path("C:/Program Files (x86)/Eclipse/Sumo/tools/xml/xml2csv.py"),
    ]

    for p in candidates:
        if p.exists():
            return p.resolve()

    raise FileNotFoundError(
        "Unable to find xml2csv.py"
        "Define SUMO_HOME (recommended) or pass xml2csv_path to runSim()"
    )

                  
# -----------------------------------------------------------------------------
# -------------------------------- CREATE FLOWS -------------------------------
# ---------------------------- CARS AND PEDESTRIANS ---------------------------
# -----------------------------------------------------------------------------

"""
Constructs a flow with the respective route (will later be added to the XML)
"""
def add_flow(fid,   # flow id
             route_edges,   # string with the route, ex: "A0B0 B0C0 C0D0 D0E0"
             start, # time when it starts
             end,   # time when it ends
             percentage,    # percentage of total agent i want in the flow
             num_agents,    # total number of agents, before the percentage
             vtype, # type of vehicle
             root,  # the father XML where the flow will be added
             depart_lane=None): # optional, more for buses
    # Compute number of vehicles for this flow
    n_vehicles = int(round(num_agents * percentage))
    if n_vehicles <= 0:
        return None

    # Create route / routeDistribution entry
    # route_edges can be:
    #   - str: a single route edges string (old behavior)
    #   - list: [(edges_str, prob), ...] to build a <routeDistribution>
    if isinstance(route_edges, (list, tuple)):
        rd_id = f"rd_{fid}"
        rd_el = ET.SubElement(root, "routeDistribution", attrib={"id": rd_id})
        for i, item in enumerate(route_edges):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                edges_str, prob = item
            else:
                edges_str, prob = item, 1.0
            ET.SubElement(
                rd_el,
                "route",
                attrib={
                    "edges": str(edges_str),
                    "probability": str(prob),
                },
            )
        route_ref = rd_id
    else:
        route_id = f"r_{fid}"
        ET.SubElement(root, "route", attrib={"id": route_id, "edges": route_edges})
        route_ref = route_id

    # Calculate flow frequency (vehicles per period)
    period = max(1, (end - start) / n_vehicles)

    flow_attrib = {
        "id": fid,
        "type": vtype,
        "begin": str(start),
        "end": str(end),
        "period": f"{period:.2f}",
        "route": route_ref,
    }
    if depart_lane is not None:
        flow_attrib["departLane"] = str(depart_lane)

    flow_el = ET.SubElement(root, "flow", attrib=flow_attrib)
    return flow_el

# -----------------------------------------------------------------------------

"""
Makes sure that the time window's division for the rush hours sum to 1
"""
def _validate_windows_sum_to_one(rush_windows_public, tol=1e-6):
    s = sum(w[2] for w in rush_windows_public)
    if abs(s - 1.0) > tol:
        raise ValueError(f"rush_windows_public need to sum to 1.0 (current sum value {s}).")

# -----------------------------------------------------------------------------

"""
Allocates people per public transports rush window:
Takes the "time windows" and the percentage of people in that time window
Returns a 
"""
def _allocate_people_per_window(num_public_people, rush_windows_public):
    per_window = []
    remaining = num_public_people
    for idx, (start, end, p) in enumerate(rush_windows_public):
        if idx < len(rush_windows_public) - 1:
            n = int(round(num_public_people * p))
            n = max(0, min(n, remaining))
        else:
            n = remaining
        per_window.append((start, end, n))
        remaining -= n
    return per_window

# -----------------------------------------------------------------------------

"""
Get's the lane's edge 
"""
def _edge_from_lane(lane_id: str) -> str:
    # "A2B2_0" -> "A2B2"
    return lane_id.rsplit("_", 1)[0]

# -----------------------------------------------------------------------------

"""
Returns the posicion of then "center" of the bus stop
It will be used to define the starting/ending point of the civilians
"""
def _stop_mid_pos(busstop_defs, stop_id: str) -> float:
    d = busstop_defs[stop_id]
    start = float(d["startPos"])
    end = float(d["endPos"])
    return (start + end) / 2.0

# -----------------------------------------------------------------------------

"""
    Creates <personFlow> elements (instead of explicit <person>) based on per-window allocations.

    For each time window (start, end, nwin):
      - Distributes the nwin people across the provided civillian_rides patterns in a simple cyclic way
        (same pattern selection logic as before, but aggregated into flows).
      - Creates one <personFlow> per (window, ride_pattern) with:
          begin/end set to the window
          period chosen so that ~count people are generated within the window
      - Adds a single <ride> child to define the PT plan.

    This keeps the "rush hour" effect: higher nwin -> smaller period -> more people per time.
"""
def _append_personflows_to_root(root, per_window, civillian_rides, busstop_defs):
    """Append <personFlow> elements.

    People are distributed across time windows (per_window). Within each window, they are
    distributed across the PT ride patterns (civillian_rides) either by:
      - explicit weights (keys 'prob' or 'weight' in each ride dict), or
      - round-robin cycling (old behavior) if no weights are provided.

    Note: SUMO does not support using <routeDistribution> for <ride> stages, so we model
    'route choice' for PT by creating multiple personFlows (one per pattern).
    """
    ride_list = list(civillian_rides)
    if not ride_list:
        raise ValueError("civillian_rides vazio. Precisas de pelo menos um padrão PT.")

    # Optional explicit weights per ride pattern
    has_weights = any(("prob" in r or "weight" in r) for r in ride_list)
    if has_weights:
        raw = [float(r.get("prob", r.get("weight", 1.0))) for r in ride_list]
        raw = [max(0.0, x) for x in raw]
        total = sum(raw)
        if total <= 0:
            weights = [1.0 / len(raw)] * len(raw)
        else:
            weights = [x / total for x in raw]
    else:
        weights = None

    pf_id = 0
    pid_cursor = 0  # keeps cycling consistent across windows when no weights are given

    for (start, end, nwin) in per_window:
        if nwin <= 0:
            continue

        # Decide counts per pattern for this window
        if weights is not None:
            counts = []
            remaining = int(nwin)
            for i, w in enumerate(weights):
                if i < len(weights) - 1:
                    c = int(round(nwin * w))
                    c = max(0, min(c, remaining))
                else:
                    c = remaining
                counts.append(c)
                remaining -= c
        else:
            counts = [0] * len(ride_list)
            for _ in range(int(nwin)):
                idx = pid_cursor % len(ride_list)
                counts[idx] += 1
                pid_cursor += 1

        duration = float(end) - float(start)

        for i, count in enumerate(counts):
            if count <= 0:
                continue

            r = ride_list[i]

            # Preferido: from_stop (spawn na paragem)
            if "from_stop" in r:
                from_stop = r["from_stop"]
                lane_id = busstop_defs[from_stop]["lane"]
                from_edge = _edge_from_lane(lane_id)
                depart_pos = _stop_mid_pos(busstop_defs, from_stop)
            else:
                # fallback: from_edge + (optional) departPos
                from_edge = r["from_edge"]
                depart_pos = float(r.get("departPos", 0))

            to_stop = r["to_stop"]
            line = r["line"]

            period = max(1.0, duration / float(count))

            pf_el = ET.SubElement(
                root,
                "personFlow",
                attrib={
                    "id": f"pf_{pf_id}",
                    "begin": str(start),
                    "end": str(end),
                    "period": f"{period:.2f}",
                    "departPos": f"{depart_pos:.2f}",
                },
            )
            ET.SubElement(
                pf_el,
                "ride",
                attrib={
                    "from": from_edge,
                    "busStop": to_stop,
                    "lines": line,
                },
            )
            pf_id += 1

# -----------------------------------------------------------------------------

"""
Constructs a flow with the respective route for people (will later be added to the XML)
"""
def add_people_flow(root, flows_template, num_private, private_vtype):
    """
    Reusa o teu add_flow tal como está.
    """
    for flow in sorted(flows_template["private_flows"], key=lambda f: f[2]):
        fid, route_edges, start, end, percentage = flow
        add_flow(fid, route_edges, start, end, percentage, num_private, private_vtype, root)

# -----------------------------------------------------------------------------

def _reorder_departure_elements(root):
    timed = [el for el in list(root) if el.tag in ("flow", "personFlow")]
    if not timed:
        return
    for el in timed:
        root.remove(el)
    timed.sort(key=lambda el: float(el.get("begin", "0")))
    for el in timed:
        root.append(el)

# -----------------------------------------------------------------------------

"""
Generates a .rou.xml with:
    - <vType> for cars
    - <route> and <flow> for private cars (distributed along the different private_flows)
    - <person> with <ride> for public transport passengers (distributed along the rush_windows_public)
IMPPORTANTE: BUS AND THER LINES WERE PREVIOUSLY DONNE OTHER FILES (bus_routes.rou.xml and bus_stops.add.xml) 
"""

def createFlowFile(
    out_path,   # Where to save the XML
    num_agents, # Number of total agents in the Simulation
    acceptance_rate_public,     # Percentage of people that are using public transports
    flows_template,     # Has the flows for the cars with an fid (flow id), the path, the starting time, the end time, percentage the total cars (rush hours)
    rush_windows_public,    # The rush hours for the civillians generation:[(start, end, percent_do_total_diario_public), ...] sums to 1.0
    civillian_rides,   # civillian rides, ex: pt_rides = [{"from_stop": "BS_L1_0", "to_stop": "BS_L1_2", "line": "L1"},
    busstop_defs,   # The dictionary of bus stops used in the beggining
    private_vtype="car",
    seed=42,
):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Total number of people is split between private and public
    share_public_people = max(0.0, min(1.0, float(acceptance_rate_public)))
    num_public_people = int(round(num_agents * share_public_people))
    num_private = max(0, num_agents - num_public_people)

    rng = random.Random(seed)

    # Root element
    root = ET.Element(
        "routes",
        attrib={
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:noNamespaceSchemaLocation": "http://sumo.dlr.de/xsd/routes_file.xsd",
        },
    )

    # ------------ CAR'S PART ------------ 

    # vType car
    ET.SubElement(
        root,
        "vType",
        attrib={
            "id": private_vtype,
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

    # Add private flows (sorted by start time to avoid SUMO warnings)
    for flow in sorted(flows_template["private_flows"], key=lambda f: f[2]):
        fid, route_edges, start, end, percentage = flow
        add_flow(fid, route_edges, start, end, percentage, num_private, private_vtype, root)


    # ------------ PEOPLE'S PART ------------ 

    # Validaty check to ensure that the rush_windows_public sum to one (or is very close to)
    _validate_windows_sum_to_one(rush_windows_public)

    # Alocate with the division logics, but with ajustments (round) to make sure the numbers are ok
    per_window = _allocate_people_per_window(num_public_people, rush_windows_public)

    _append_personflows_to_root(
        root=root,
        per_window=per_window,
        civillian_rides=civillian_rides,
        busstop_defs=busstop_defs,
    )

    # SUMO requires departures sorted by time; reorder flow/personFlow elements.
    _reorder_departure_elements(root)
    
    # Write to disk
    ET.indent(ET.ElementTree(root), space="  ", level=0)
    ET.ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Demand file written: {out_path.resolve()}")
    return out_path


# -----------------------------------------------------------------------------
# ------------------------------ RUNNING IN SUMO ------------------------------
# ------------------------- ONLY ONE SIMULATION (DAY) -------------------------
# -----------------------------------------------------------------------------


"""
    Calls SUMO in batch mode using multiple route files (comma-separated).
    produces tripinfo, emissions and personinfo output.
    Returns (returncode, stdout, stderr).
"""
def runSUMO(route_files,
            netfile,
            tripinfo_out,
            emissions_out,
            personinfo_out,
            sumo_binary="sumo",
            additional_files=None,
            additional_sumo_args=None):
    
    netfile = Path(netfile)
    tripinfo_out = Path(tripinfo_out)
    emissions_out = Path(emissions_out)
    personinfo_out = Path(personinfo_out)
    tripinfo_out.parent.mkdir(parents=True, exist_ok=True)
    emissions_out.parent.mkdir(parents=True, exist_ok=True)
    personinfo_out.parent.mkdir(parents=True, exist_ok=True)

    # Putting the files in the correct format
    route_arg = ",".join(str(Path(f)) for f in route_files)

    args = [
        str(sumo_binary),
        "-n", str(netfile),
        "-r", str(route_arg),
        "--tripinfo-output", str(tripinfo_out),
        "--device.emissions.probability", "1.0",
        "--emission-output", str(emissions_out),
        "--personinfo-output", str(personinfo_out),
        "--duration-log.statistics",
        "--no-warnings",
        # we can define --seed here for reproducibility
    ]

    if additional_files:
        # SUMO accepts a comma-separated list for multiple additional files
        if isinstance(additional_files, (str, Path)):
            additional_files = [additional_files]

        add_arg = ",".join(str(Path(f)) for f in additional_files)
        args += ["--additional-files", add_arg]

    if additional_sumo_args:
        args += list(additional_sumo_args)

    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr


# -----------------------------------------------------------------------------
# ---------------------------------- POLICIES ---------------------------------
# ---------------------------------- UPDATES ----------------------------------
# -----------------------------------------------------------------------------


"""Simple linear evolution: acceptance = base + slope * day (clamped 0..1)"""
def linear_acceptance(base, slope, day):
    val = base + slope * day
    return max(0.0, min(1.0, val))

# -----------------------------------------------------------------------------

"""Logistic curve for adoption: L / (1 + exp(-k*(day-x0)))"""
def logistic_acceptance(L, k, x0, day):
    return L / (1.0 + math.exp(-k * (day - x0)))

# -----------------------------------------------------------------------------

"""
    Compute probability of choosing public transport using a Multinomial Logit (softmax) over utilities.
    Returns probability in [0,1].
    weights: e.g. {'time': -1.0, 'cost': -0.5, 'pollution': -0.2}
"""
def utility_preference(time_private, time_public, cost_private, cost_public, 
                       pollution_private, pollution_public, weights):
    # utility = w_time * time + w_cost * cost + w_pollution * pollution
    u_private = weights.get("time", 0.0) * time_private + weights.get("cost", 0.0) * cost_private + weights.get("pollution", 0.0) * pollution_private
    u_public = weights.get("time", 0.0) * time_public + weights.get("cost", 0.0) * cost_public + weights.get("pollution", 0.0) * pollution_public

    # Avoid overflow
    maxu = max(u_private, u_public)
    exp_priv = math.exp(u_private - maxu)
    exp_pub = math.exp(u_public - maxu)
    p_public = exp_pub / (exp_priv + exp_pub)
    return p_public

# -----------------------------------------------------------------------------

"""
    Updates the acceptance rate for the linear and logistic policies
    Return acceptance_rate_public for given day.
"""
def updatePolicy(policy, day):
    if policy.get("type") == "linear":
        return linear_acceptance(policy.get("base", 0.1), policy.get("slope", 0.02), day)
    elif policy.get("type") == "logistic":
        return logistic_acceptance(policy.get("L", 0.9), policy.get("k", 0.3), policy.get("x0", 3), day)
    else:
        # default constant acceptance
        return policy.get("base", 0.1)


# -----------------------------------------------------------------------------
# ---------------------------------- CLEANING ---------------------------------
# ------------------------------- PRE PROCESSING ------------------------------
# -----------------------------------------------------------------------------


def orderSpawn(df):
    ids = df["tripinfo_id"].astype(str)

    # flow_id: só existe se o id tiver "flow_<n>"
    flow_extracted = ids.str.extract(r"flow_(\d+)")[0]
    df["flow_id"] = pd.to_numeric(flow_extracted, errors="coerce").astype("Int64")

    # car_num: só existe se o id acabar em ".<n>"
    car_extracted = ids.str.extract(r"\.(\d+)$")[0]
    df["car_num"] = pd.to_numeric(car_extracted, errors="coerce").astype("Int64")

    # Decide onde entram os que NÃO são flow_*.<n>:
    # - se quiseres flows primeiro (como tinhas), mete NaN bem grande
    sort_flow = df["flow_id"].fillna(10**9)
    sort_car  = df["car_num"].fillna(10**9)

    df = (
        df.assign(_sort_flow=sort_flow, _sort_car=sort_car)
          .sort_values(by=["_sort_flow", "_sort_car", "tripinfo_id"], ascending=[True, True, True])
          .drop(columns=["_sort_flow", "_sort_car", "car_num"])
          .reset_index(drop=True)   # <<< ADICIONA ISTO
    )

    return df


def getClean(f):
    df = pd.read_csv(f, sep=";")

    match = re.search(r"sim(\d+)_day(\d+)", str(f))
    sim = int(match.group(1)) if match else -1
    day = int(match.group(2)) if match else -1

    # ordenar e garantir índice limpo
    if "tripinfo_id" in df.columns:
        df = orderSpawn(df)
    df = df.reset_index(drop=True)

    # CRUCIAL: cria com o mesmo index
    df_clean = pd.DataFrame(index=df.index)

    df_clean["entity"] = "vehicle"
    df_clean["tripinfo_id"] = df.get("tripinfo_id")
    df_clean["tripinfo_vType"] = df.get("tripinfo_vType")

    vtype = df_clean["tripinfo_vType"].astype(str).str.lower()
    df_clean["mode"] = vtype.apply(lambda s: "bus" if "bus" in s else "car")

    df_clean["day"] = day
    df_clean["sim"] = sim

    df_clean["CO2_abs"] = df.get("emissions_CO2_abs", 0.0)

    df_clean["departDelay"] = df.get("tripinfo_departDelay", 0.0)
    df_clean["waitingTime"] = df.get("tripinfo_waitingTime", 0.0)
    df_clean["waitingCount"] = df.get("tripinfo_waitingCount", 0)
    df_clean["timeLoss"] = df.get("tripinfo_timeLoss", 0.0)

    df_clean["duration"] = df.get("tripinfo_duration", 0.0)
    df_clean["routeLength"] = df.get("tripinfo_routeLength", 0.0)

    dd = pd.to_numeric(df_clean["departDelay"], errors="coerce").fillna(0.0)
    dur = pd.to_numeric(df_clean["duration"], errors="coerce").fillna(0.0)
    df_clean["effectiveTime"] = dd + dur

    df_clean["flow_id"] = df.get("flow_id", pd.Series([pd.NA] * len(df), dtype="Int64"))

    return df_clean



def getCleanPerson(f):
    df = pd.read_csv(f, sep=";")

    match = re.search(r"sim(\d+)_day(\d+)", str(f))
    sim = int(match.group(1)) if match else -1
    day = int(match.group(2)) if match else -1

    df = df.reset_index(drop=True)

    out = pd.DataFrame(index=df.index)

    out["entity"] = "person"
    out["mode"] = "person"

    out["tripinfo_id"] = df.get("personinfo_id", df.get("id"))
    out["tripinfo_vType"] = df.get("personinfo_type", df.get("type", "person"))

    out["day"] = day
    out["sim"] = sim

    out["CO2_abs"] = 0.0
    out["departDelay"] = 0.0

    out["waitingTime"] = df.get("personinfo_waitingTime", df.get("waitingTime", 0.0))
    out["waitingCount"] = 0
    out["timeLoss"] = df.get("personinfo_timeLoss", df.get("timeLoss", 0.0))

    out["duration"] = df.get("personinfo_duration", df.get("duration", 0.0))

    out["travelTime"] = df.get(
        "personinfo_traveltime",
        df.get("personinfo_travetime", df.get("traveltime", df.get("travetime", df.get("travelTime", 0.0))))
    )

    out["routeLength"] = 0.0
    out["flow_id"] = pd.Series([pd.NA] * len(df), dtype="Int64")

    wt = pd.to_numeric(out["waitingTime"], errors="coerce").fillna(0.0)
    tt = pd.to_numeric(out["travelTime"], errors="coerce").fillna(0.0)
    dur = pd.to_numeric(out["duration"], errors="coerce").fillna(0.0)
    out["effectiveTime"] = (wt + tt).where((tt > 0) | (wt > 0), dur)

    return out




def csvCleaner(policy_folder, policy_name, clean):
    policy_folder = Path(policy_folder)

    trip_files = sorted(
        p for p in policy_folder.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".csv"
        and p.name.startswith("tripinfo_sim")
    )

    person_files = sorted(
        p for p in policy_folder.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".csv"
        and p.name.startswith("personinfo_sim")
    )

    if not trip_files and not person_files:
        print(f"No tripinfo/personinfo CSV files found in {policy_folder}. Skipping cleaning.")
        return pd.DataFrame()

    parts = []
    for f in trip_files:
        parts.append(getClean(str(f)))

    for f in person_files:
        parts.append(getCleanPerson(str(f)))

    df_global = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    
    clean.mkdir(parents=True, exist_ok=True)

    out_file = clean / f"{policy_name}.csv"
    df_global.to_csv(out_file, index=False)

    return df_global



# -----------------------------------------------------------------------------
# ------------------------- KPI aggregation - Dynamic -------------------------
# -----------------------------------------------------------------------------

def summarize_daily_kpis(df: pd.DataFrame, policy_id: str = "") -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    # garante colunas
    if "entity" not in df.columns:
        df = df.copy()
        df["entity"] = "vehicle"
    if "mode" not in df.columns:
        # fallback antigo: usa tripinfo_vType
        df = df.copy()
        df["mode"] = df.get("tripinfo_vType", "unknown")

    grouped = (
        df.groupby(["sim", "day", "entity", "mode"], dropna=False)
          .agg(
              n=("tripinfo_id", "count"),

              mean_effectiveTime=("effectiveTime", "mean"),
              mean_duration=("duration", "mean"),
              mean_waitingTime=("waitingTime", "mean"),
              mean_departDelay=("departDelay", "mean"),
              mean_timeLoss=("timeLoss", "mean"),

              mean_routeLength=("routeLength", "mean"),

              sum_CO2_abs=("CO2_abs", "sum"),
              mean_CO2_abs=("CO2_abs", "mean"),
          )
          .reset_index()
    )

    if policy_id:
        grouped.insert(0, "policy_id", policy_id)

    print(grouped[["entity", "mode", "n", "mean_effectiveTime", "sum_CO2_abs"]])

    return grouped


# ----------------------------
# Dynamic update from KPIs
# ----------------------------

def update_acceptance_from_kpis(
    kpis_day: pd.DataFrame,
    prev_acceptance: float,
    policy: Dict[str, Any],
    private_mode: str = "car",     # veículos privados
    bus_mode: str = "bus",         # veículos PT (para CO2/dist)
    public_entity: str = "person", # usar pessoas para tempo público
) -> Tuple[float, Optional[float]]:

    lr = float(policy.get("learning_rate", 0.35))
    min_a = float(policy.get("min_acceptance", 0.0))
    max_a = float(policy.get("max_acceptance", 1.0))

    weights = policy.get("weights", {"time": -0.002, "cost": -0.30, "pollution": -0.000001})

    car_cost_per_km = float(policy.get("car_cost_per_km", 0.20))
    bus_fare = float(policy.get("bus_fare", 1.50))
    bus_cost_per_km = float(policy.get("bus_cost_per_km", 0.0))

    def pick(entity: str, mode: str):
        r = kpis_day[(kpis_day["entity"] == entity) & (kpis_day["mode"] == mode)]
        return None if r.empty else r.iloc[0]

    car = pick("vehicle", private_mode)
    pax = kpis_day[kpis_day["entity"] == public_entity]
    pax = None if pax.empty else pax.iloc[0]
    busveh = pick("vehicle", bus_mode)

    # Se hoje não houve carros ou pessoas, não atualiza
    if car is None or pax is None:
        next_a = max(min_a, min(max_a, float(prev_acceptance)))
        print("Error KPIs policy")
        return next_a, None

    # TEMPO: carro vs passageiro PT
    time_private = float(car.get("mean_effectiveTime", car.get("mean_duration", 0.0)))
    time_public  = float(pax.get("mean_effectiveTime", pax.get("mean_duration", 0.0)))

    # DISTÂNCIA/CUSTO: carro usa routeLength; PT pode usar distância média do bus (se existir)
    dist_private_km = float(car.get("mean_routeLength", 0.0)) / float(car.get("n"))
    cost_private = car_cost_per_km * dist_private_km

    if busveh is not None:
        dist_public_km = float(busveh.get("mean_routeLength", 0.0)) / float(busveh.get("n"))
    else:
        dist_public_km = 0.0
    cost_public = bus_fare + bus_cost_per_km * dist_public_km

    # POLUIÇÃO: carro = por veículo; PT = CO2_total_bus / nº passageiros (se tiver buses)
    pol_private = float(car.get("sum_CO2_abs", 0.0))
    if busveh is not None:
        pol_public = float(busveh.get("sum_CO2_abs", 0.0))
    else:
        pol_public = 0.0

    pref_public = utility_preference(
        time_private, time_public,
        cost_private, cost_public,
        pol_private, pol_public,
        weights=weights,
    )

    next_acceptance = (1.0 - lr) * float(prev_acceptance) + lr * float(pref_public)
    next_acceptance = max(min_a, min(max_a, next_acceptance))
    return next_acceptance, float(pref_public)


# -----------------------------------------------------------------------------
# ------------------------------- RUN SIMULATION ------------------------------
# --------------------------------- FOR N DAYS --------------------------------
# -----------------------------------------------------------------------------


"""
    Corre várias simulações, vários dias.
    Cada dia:
      - gera um demand file (car flows + persons)
      - corre SUMO com route files: [static_route_files..., demandfile]
      - exporta tripinfo, emissions e personinfo
      - converte tripinfo/personinfo para CSV
"""
def runSim(
    n_simulations=1,    # Number of simulations
    days_per_sim=7,     # Number of days per simualtion
    policy=None,        # The chosen policy
    num_agents_global=200,      # Total number of "agents", cars and people
    flows_template=None,    # The first flow (cars and people)
    rush_windows_public=None,   
    civillian_rides=None,
    busstop_defs=None,
    static_route_files=None,    # Buses route
    flows_dir=Path("sumo_runs/flows"),  # Where to save the daily flows
    raw_out_dir=Path("sumo_runs/raw_xml"),  # XMLs 
    csv_out_dir=Path("sumo_runs/raw_csv"),  # CSVs
    sumo_net_file=Path("automate_flow/core/manhattan.net.xml"),
    sumo_binary="sumo",
    additional_files=None,       # ex: bus stops .add.xml, etc
    additional_sumo_args=None,
    private_vtype="car",
    public_vtype="bus",  # ainda pode ser útil nos KPIs, mesmo que createFlowFile não use
    xml2csv_path=None,
    seed_base=42,
):
    # If no policy, then Static
    if policy is None:
        policy = {"id": "policy_default", "type": "linear", "base": 0.05, "slope": 0.05}

    if flows_template is None:
        raise ValueError("flows_template is None. You nedd to pass it.")

    if rush_windows_public is None or civillian_rides is None or busstop_defs is None:
        raise ValueError(
            "Para simular pessoas (person+ride), precisas de passar: "
            "rush_windows_public, civillian_rides e busstop_defs."
        )

    flows_dir = Path(flows_dir); flows_dir.mkdir(parents=True, exist_ok=True)
    raw_out_dir = Path(raw_out_dir); raw_out_dir.mkdir(parents=True, exist_ok=True)
    csv_out_dir = Path(csv_out_dir); csv_out_dir.mkdir(parents=True, exist_ok=True)

    # resolve sumo binary + xml2csv
    sumo_binary_resolved = resolve_sumo_binary(str(sumo_binary) if sumo_binary else None)
    xml2csv_resolved = resolve_xml2csv_path(xml2csv_path, sumo_binary=sumo_binary_resolved)

    policy_id = policy.get("id", "policy")

    # prepara lista de routes estáticos
    static_route_files = [Path(p) for p in (static_route_files or [])]

    for sim_id in range(1, n_simulations + 1):
        print(f"Starting simulation {sim_id}/{n_simulations} (policy={policy.get('id')})")

        acceptance = float(policy.get("base", 0.1))
        acceptance_log: List[Dict[str, Any]] = []

        for day in range(1, days_per_sim + 1):
            print(f"  Simulation {sim_id} Day {day}: acceptance_rate_public = {acceptance:.3f}")

            # Generate a flows xml for this day (car flows + persons)
            flowfile = flows_dir / f"flows_sim{sim_id}_day{day}_{policy_id}.rou.xml"
            createFlowFile(
                out_path=flowfile,
                num_agents=num_agents_global,
                acceptance_rate_public=acceptance,
                flows_template=flows_template,
                rush_windows_public=rush_windows_public,
                civillian_rides=civillian_rides,
                busstop_defs=busstop_defs,
                private_vtype=private_vtype,
                seed=seed_base + sim_id * 1000 + day,
            )

            # Output filenames
            tripinfo_out   = raw_out_dir / f"tripinfo_sim{sim_id}_day{day}_{policy_id}.xml"
            emissions_out  = raw_out_dir / f"emissions_sim{sim_id}_day{day}_{policy_id}.xml"
            personinfo_out = raw_out_dir / f"personinfo_sim{sim_id}_day{day}_{policy_id}.xml"

            # Route files deste dia = (buses/routes fixos) + (demand do dia)
            route_files_today = [*static_route_files, flowfile]

            # Run SUMO once for this day
            ret, out, err = runSUMO(
                route_files=route_files_today,
                netfile=sumo_net_file,
                tripinfo_out=tripinfo_out,
                emissions_out=emissions_out,
                personinfo_out=personinfo_out,
                sumo_binary=sumo_binary_resolved,
                additional_files=additional_files,
                additional_sumo_args=additional_sumo_args,
            )

            if ret != 0: print(f"SUMO returned non-zero code {ret}. stderr:\n{err}")
            else: print(f"Simulation{sim_id}, day {day}: DONE.")

            # tripinfo.xml -> csv
            tripinfo_csv_out = csv_out_dir / f"tripinfo_sim{sim_id}_day{day}_{policy_id}.csv"
            if tripinfo_out.exists():
                cmd = [sys.executable, str(xml2csv_resolved), str(tripinfo_out), "--output", str(tripinfo_csv_out)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"tripinfo CSV converted: {tripinfo_csv_out}")
                else:
                    print(f"TRIPINFO CONVERSION FAILED:\n{result.stderr}")
            else:
                print(f"tripinfo XML NOT FOUND: {tripinfo_out}")

            # personinfo.xml -> csv
            personinfo_csv = csv_out_dir / f"personinfo_sim{sim_id}_day{day}_{policy_id}.csv"
            if personinfo_out.exists():
                cmd = [sys.executable, str(xml2csv_resolved), str(personinfo_out), "--output", str(personinfo_csv)]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"personinfo CSV converted: {personinfo_csv}")
                else:
                    print(f"PERSONINFO CONVERSION FAILED:\n{result.stderr}")
            else:
                print(f"personinfo XML NOT FOUND: {personinfo_out}")

            df_veh = getClean(str(tripinfo_csv_out))
            df_pax = getCleanPerson(str(personinfo_csv))
            df_day_clean = pd.concat([df_veh, df_pax], ignore_index=True)
            kpis_day = summarize_daily_kpis(df_day_clean, policy_id=policy_id)

            # Guardar KPIs por dia (append)
            kpi_path = csv_out_dir / f"daily_kpis_{policy_id}_sim{sim_id}.csv"
            write_header = not kpi_path.exists()
            kpis_day.to_csv(kpi_path, mode="a", header=write_header, index=False)
            
            # Decide acceptance for this day
            if policy.get("type") in ("linear", "logistic"):
                next_a = updatePolicy(policy, day - 1)

                acceptance_log.append({
                        "sim": sim_id,
                        "day": day,
                        "acceptance_used": float(acceptance),
                        "acceptance_next": float(next_a),
                    })

                acceptance = float(next_a)
                print(f"    public transport update -> acceptance_next={acceptance:.3f}")
            elif policy.get("type") == "utility":
                try:
                    next_a, pref = update_acceptance_from_kpis(
                        kpis_day,
                        acceptance,
                        policy,
                        private_mode=private_vtype,  # "car"
                        bus_mode=public_vtype,       # "bus"
                        public_entity="person",      # tempo público vem das pessoas
                    )

                    acceptance_log.append({
                        "sim": sim_id,
                        "day": day,
                        "acceptance_used": float(acceptance),
                        "pref_public": pref,
                        "acceptance_next": float(next_a),
                    })

                    acceptance = float(next_a)
                    print(f"    utility update -> pref_public={pref} acceptance_next={acceptance:.3f}")

                except Exception as e:
                    print(f"    utility update failed (keeping acceptance): {e}")
            else:
                acceptance = float(policy.get("base", 0.1))
                

        # Save acceptance log (if utility)
        if acceptance_log:
            log_path = csv_out_dir / f"acceptance_log_{policy_id}_sim{sim_id}.csv"
            pd.DataFrame(acceptance_log).to_csv(log_path, index=False)
            print(f"Saved acceptance log: {log_path.resolve()}")

    print("All simulations completed.")
    print(f"Individual CSVs saved to: {csv_out_dir}")
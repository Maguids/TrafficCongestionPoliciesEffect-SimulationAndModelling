import random
import collections
from pathlib import Path
import xml.etree.ElementTree as ET

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
                    "frequency": str(prob),
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
    
    # Write to disk
    ET.indent(ET.ElementTree(root), space="  ", level=0)
    ET.ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
    print(f"Demand file written: {out_path.resolve()}")
    return out_path



def main():
    out_dir = Path("out_test")
    out_dir.mkdir(exist_ok=True)

    # --- Exemplo de busStops (o teu formato)
    busstop_defs = {
        "BS_L1_0": {"lane": "A2J2_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L1_1": {"lane": "C2J0_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L1_2": {"lane": "D2J3_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},

        "BS_L2_0": {"lane": "C0J9_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L2_1": {"lane": "C2J1_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L2_2": {"lane": "C3J4_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},

        "BS_L3_0": {"lane": "A0J8_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L3_1": {"lane": "E0J7_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L3_2": {"lane": "E4J5_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
        "BS_L3_3": {"lane": "A4J6_0", "startPos": 10, "endPos": 20, "friendlyPos": "true"},
    }

    # --- Car flows (percentagens diárias dos carros -> devem somar ~1.0)
    flows_template = {
        "private_flows": [
        # Cada tuplo: (flow_id, route_edges_or_distribution, start, end, percentage)
        # Aqui, route_edges_or_distribution é uma LISTA de (edges, prob) -> cria <routeDistribution>
        (
            "flow_0",
            [
                ("A2J2 J2B2 B2C2 C2J0 J0D2 D2J3 J3E2", 0.25),
                ("C0J9 J9C1 C1C2 C2J1 J1C3 C3B3 B3A3",0.25),
                ("A0A1 A1B1 B1B2 B2C2 C2J0 J0D2 D2D3 D3D4",0.25),
                ("C4B4 B4A4 A4J6 J6A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
            ],
            0, 6*3600, 0.10
        ),
        (
            "flow_1",
            [
                ("A2J2 J2B2 B2C2 C2J0 J0D2 D2J3 J3E2", 0.25),
                ("C0J9 J9C1 C1C2 C2J1 J1C3 C3B3 B3A3",0.25),
                ("A0A1 A1B1 B1B2 B2C2 C2J0 J0D2 D2D3 D3D4",0.25),
                ("C4B4 B4A4 A4J6 J6A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
            ],
            6*3600, 9*3600, 0.50
        ),
        (
            "flow_2",
            [
                ("A2J2 J2B2 B2C2 C2J0 J0D2 D2J3 J3E2", 0.25),
                ("C0J9 J9C1 C1C2 C2J1 J1C3 C3B3 B3A3",0.25),
                ("A0A1 A1B1 B1B2 B2C2 C2J0 J0D2 D2D3 D3D4",0.25),
                ("C4B4 B4A4 A4J6 J6A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
            ],
            9*3600, 16*3600, 0.30
        ),
        (
            "flow_3",
            [
                ("A2J2 J2B2 B2C2 C2J0 J0D2 D2J3 J3E2", 0.25),
                ("C0J9 J9C1 C1C2 C2J1 J1C3 C3B3 B3A3",0.25),
                ("A0A1 A1B1 B1B2 B2C2 C2J0 J0D2 D2D3 D3D4",0.25),
                ("C4B4 B4A4 A4J6 J6A3 A3B3 B3B2 B2B1 B1B0 B0A0",0.25)
            ],
            16*3600, 24*3600, 0.10
        ),

        ]
    }

    # --- PT rush windows (percentagens do total diário de PESSOAS PT -> somar 1.0)
    rush_windows_public = [
        (0, 6*3600, 0.20),
        (6*3600, 20*3600, 0.70),
        (20*3600, 24*3600, 0.10),
    ]

    # --- Padrões PT (spawn no from_stop e ride até to_stop)
    civillian_rides = [
        {"from_stop": "BS_L1_0", "to_stop": "BS_L1_1", "line": "L1"},
        {"from_stop": "BS_L1_1", "to_stop": "BS_L1_2", "line": "L1"},
        {"from_stop": "BS_L2_0", "to_stop": "BS_L2_1", "line": "L2"},
        {"from_stop": "BS_L2_1", "to_stop": "BS_L2_2", "line": "L2"},
        {"from_stop": "BS_L3_0", "to_stop": "BS_L3_1", "line": "L3"},
        {"from_stop": "BS_L3_1", "to_stop": "BS_L3_2", "line": "L3"},
        {"from_stop": "BS_L3_2", "to_stop": "BS_L3_3", "line": "L3"},
    ]

    num_agents = 10000
    acceptance_rate_public = 0.30  # 30% pessoas em PT

    demand_path = createFlowFile(
        out_path=out_dir / "demand.rou.xml",
        num_agents=num_agents,
        acceptance_rate_public=acceptance_rate_public,
        flows_template=flows_template,
        rush_windows_public=rush_windows_public,
        civillian_rides=civillian_rides,
        busstop_defs=busstop_defs,
        private_vtype="car",
        seed=42,
    )

    print("\nAgora corre SUMO (ajusta o path da tua net):")
    print("  sumo-gui -n grid.net.xml -r out_test/demand.rou.xml,out_test/buses.rou.xml")
    print("ou headless:")
    print("  sumo -n grid.net.xml -r out_test/demand.rou.xml,out_test/buses.rou.xml --no-step-log")


if __name__ == "__main__":
    main()
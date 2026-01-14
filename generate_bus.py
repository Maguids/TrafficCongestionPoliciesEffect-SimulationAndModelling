from __future__ import annotations

from typing import Dict, List, Tuple, Optional, Union, Any
import xml.etree.ElementTree as ET


PublicRoute = Tuple[str, List[Tuple[str, int]]]  # (edges_str, [(busStopId, durationSec), ...])


def _indent_xml(elem: ET.Element, level: int = 0) -> None:
    """Pretty print (in-place) for ElementTree."""
    i = "\n" + "  " * level
    if len(elem):
        if not (elem.text and elem.text.strip()):
            elem.text = i + "  "
        for child in elem:
            _indent_xml(child, level + 1)
        if not (elem.tail and elem.tail.strip()):
            elem.tail = i
    else:
        if level and not (elem.tail and elem.tail.strip()):
            elem.tail = i


def generate_sumo_bus_files(
    public_routes: List[PublicRoute],
    busstop_defs: Optional[Dict[str, Dict[str, Union[str, int, float]]]] = None,
    *,
    # naming (para ficar tipo os teus: r_L1 / bus_L1 / line="L1")
    line_prefix: str = "L",
    route_id_prefix: str = "r_",
    flow_id_prefix: str = "bus_",
    # flow params
    begin: Union[int, float] = 0,
    end: Union[int, float] = 3600,
    period: Union[int, float] = 600,
    departLane: str = "0",
    # vehicle type
    vtype_id: str = "bus",
    vtype_attrs: Optional[Dict[str, Union[str, int, float]]] = None,
    # bus stop defaults
    default_startPos: Union[int, float] = 10.0,
    default_endPos: Union[int, float] = 20.0,
    friendlyPos: Union[bool, str] = "true",
    # output files (opcional)
    out_routes_path: Optional[str] = None,   # e.g. "bus_routes.rou.xml"
    out_stops_path: Optional[str] = None,    # e.g. "bus_stops.add.xml"
) -> Tuple[str, str]:
    """
    Gera XMLs SUMO:
      - bus_routes.rou.xml (routes + vType + route + flow + stop)
      - bus_stops.add.xml (additional + busStop)

    busstop_defs (opcional) exemplo:
      {
        "bs_0": {"lane": "A1B1_0", "startPos": 10.0, "endPos": 20.0, "friendlyPos": "true"},
        ...
      }

    Se um busStop não tiver 'lane', tenta inferir a partir da rota:
      usa o edge com o mesmo índice do stop (fallback: último edge), e mete lane="<edge>_0".
    """

    busstop_defs = busstop_defs or {}

    # -------- inferência de "edge por stop" para defaults --------
    stop_to_edge: Dict[str, str] = {}
    for edges_str, stops in public_routes:
        edges = [e for e in edges_str.split() if e.strip()]
        if not edges:
            continue
        for j, (bs_id, _) in enumerate(stops):
            if bs_id in stop_to_edge:
                continue
            edge = edges[min(j, len(edges) - 1)]
            stop_to_edge[bs_id] = edge

    # -------- bus_routes.rou.xml --------
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    routes_root = ET.Element(
        "routes",
        {
            "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation":
                "http://sumo.dlr.de/xsd/routes_file.xsd"
        },
    )

    # vType default (bem parecido ao teu exemplo)
    if vtype_attrs is None:
        vtype_attrs = {
            "vClass": "bus",
            "length": 10,
            "maxSpeed": 10,
            "minGap": 2.5,
            "accel": 2.6,
            "decel": 4.5,
            "sigma": 0.5,
            "emissionClass": "HBEFA3/PC_G_EU6",
            "guiShape": "bus",
            "color": "blue",
            "personCapacity": 60,
        }

    vtype_el_attrs: Dict[str, str] = {"id": str(vtype_id)}
    vtype_el_attrs.update({k: str(v) for k, v in vtype_attrs.items()})
    ET.SubElement(routes_root, "vType", vtype_el_attrs)

    # routes + flows
    for i, (edges_str, stops) in enumerate(public_routes, start=1):
        line_id = f"{line_prefix}{i}"         # L1, L2, ...
        route_id = f"{route_id_prefix}{line_id}"  # r_L1, r_L2, ...
        flow_id = f"{flow_id_prefix}{line_id}"    # bus_L1, bus_L2, ...

        ET.SubElement(routes_root, "route", {"id": route_id, "edges": edges_str.strip()})

        flow_el = ET.SubElement(
            routes_root,
            "flow",
            {
                "id": flow_id,
                "type": str(vtype_id),
                "route": route_id,
                "begin": str(begin),
                "end": str(end),
                "period": str(period),
                "line": line_id,
                "departLane": str(departLane),
            },
        )

        for bs_id, dur in stops:
            ET.SubElement(flow_el, "stop", {"busStop": bs_id, "duration": str(int(dur))})

    _indent_xml(routes_root)
    routes_xml = ET.tostring(routes_root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    # -------- bus_stops.add.xml --------
    additional_root = ET.Element("additional")

    # dedup pela ordem de aparição
    seen = set()
    ordered_stops: List[str] = []
    for _, stops in public_routes:
        for bs_id, _ in stops:
            if bs_id not in seen:
                seen.add(bs_id)
                ordered_stops.append(bs_id)

    def friendly_to_str(x: Union[bool, str]) -> str:
        if isinstance(x, bool):
            return "true" if x else "false"
        return str(x)

    for bs_id in ordered_stops:
        info = busstop_defs.get(bs_id, {})
        lane = info.get("lane")
        if lane is None:
            edge = stop_to_edge.get(bs_id, "UNKNOWN")
            lane = f"{edge}_0" if edge != "UNKNOWN" else "UNKNOWN"

        startPos = info.get("startPos", default_startPos)
        endPos = info.get("endPos", default_endPos)
        fp = info.get("friendlyPos", friendlyPos)

        ET.SubElement(
            additional_root,
            "busStop",
            {
                "id": bs_id,
                "lane": str(lane),
                "startPos": str(startPos),
                "endPos": str(endPos),
                "friendlyPos": friendly_to_str(fp),
            },
        )

    _indent_xml(additional_root)
    stops_xml = ET.tostring(additional_root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    # escrever para ficheiros (se quiseres)
    if out_routes_path:
        with open(out_routes_path, "w", encoding="utf-8") as f:
            f.write(routes_xml)
    if out_stops_path:
        with open(out_stops_path, "w", encoding="utf-8") as f:
            f.write(stops_xml)

    return routes_xml, stops_xml


# ---- exemplo de uso ----
if __name__ == "__main__":

    # Duas linhas simples na tua grid:
    # L1: topo (A0->A4) e desce à direita até E4
    # L2: desce à esquerda até E0 e segue no fundo até E4
    public_routes = [
    (
        "A2J2 J2B2 B2C2 C2J0 J0D2 D2J3 J3E2",
        [("BS_L1_0", 15), ("BS_L1_1", 15), ("BS_L1_2", 15)],
    ),
    (
        "C0J9 J9C1 C1C2 C2J1 J1C3 C3J4 J4C4",
        [("BS_L2_0", 15), ("BS_L2_1", 15), ("BS_L2_2", 15)],
    ),
    (
        "A0J8 J8B0 B0C0 C0D0 D0E0 E0J7 J7E1 E1E2 E2E3 E3E4 E4J5 J5D4 D4C4 C4B4 B4A4 A4J6 J6A3 A3A2 A2A1 A1A0",
        [("BS_L3_0", 15), ("BS_L3_1", 15), ("BS_L3_2", 15), ("BS_L3_3", 15)]
    )
]

    # Paragens (lanes existem na net: <edge>_0)
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

    generate_sumo_bus_files(
        public_routes,
        busstop_defs,
        begin=0,
        end=3600*24,
        period=600,
        departLane="0",
        out_routes_path="bus_routes.rou.xml",
        out_stops_path="bus_stops.add.xml",
    )

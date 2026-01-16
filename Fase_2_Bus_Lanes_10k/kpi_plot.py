#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import glob
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np


# -----------------------------
# Config / helpers
# -----------------------------

@dataclass(frozen=True)
class Scenario:
    map_name: str
    appendix: str  # keep as str for labeling
    folder_name: str  # f"{map_name}_{appendix}"
    path: str  # full path to scenario folder


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_read_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV não encontrado: {path}")
    return pd.read_csv(path)


def find_acceptance_csv(scenario_path: str) -> Optional[str]:
    """
    Encontra o ficheiro acceptance log dentro do cenário.
    Ex.: acceptance_log_baseline_1000_sim_1.csv ou acceptance_log_baseline_1000_sim1.csv
    """
    patterns = [
        os.path.join(scenario_path, "acceptance_log_*sim*.csv"),
        os.path.join(scenario_path, "acceptance_log_*.csv"),
    ]
    matches: List[str] = []
    for p in patterns:
        matches.extend(glob.glob(p))
    matches = sorted(set(matches))
    return matches[0] if matches else None


def save_fig(fig, outpath: str) -> None:
    fig.tight_layout()
    fig.savefig(outpath, dpi=200)
    plt.close(fig)



def plot_grouped_bars_from_pivot(
    pivot: pd.DataFrame,
    title: str,
    ylabel: str,
    ax: Optional[plt.Axes] = None,
    xlabel: str = "",
    show_legend: bool = True,
    outpath: Optional[str] = None,
) -> None:
    """Barras agrupadas por dia a partir de um pivot.

    pivot: index=day, columns=labels, values=metric

    - Se `ax` for dado: desenha no eixo.
    - Se `ax` não for dado: cria figura e, se `outpath` for dado, guarda no disco.
    """
    pivot = pivot.sort_index()
    days = pivot.index.to_list()
    cols = list(pivot.columns)

    x = np.arange(len(days))
    n = max(len(cols), 1)
    width = 0.8 / n

    created_fig = False
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 3.2))
        created_fig = True
    else:
        fig = ax.figure

    for i, c in enumerate(cols):
        y = pivot[c].values
        ax.bar(x + (i - (n - 1) / 2) * width, y, width=width, label=str(c))

    ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xticklabels(days, rotation=45, ha="right")
    ax.grid(True, axis="y", alpha=0.3)
    if show_legend:
        ax.legend()

    if created_fig and outpath:
        save_fig(fig, outpath)


def kpi_filter_mode(kpis: pd.DataFrame, mode: str) -> pd.DataFrame:
    out = kpis[kpis["mode"] == mode].copy()
    out = out.sort_values(["day"])
    return out


# -----------------------------
# Overall plots per map_name
# -----------------------------

def load_scenario_data(s: Scenario) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    kpis = safe_read_csv(os.path.join(s.path, "summary_daily_kpis.csv"))
    acc_path = find_acceptance_csv(s.path)
    acc = safe_read_csv(acc_path) if acc_path else None
    return kpis, acc


def make_overall_plots_bars(map_name: str, scenarios: List[Scenario], overall_dir: str) -> None:
    """
    OVERALL (por map): small multiples por MODO, com BARRAS agrupadas por dia (appendices lado a lado).
    Output:
      - public_acceptance_overall.png (1 painel)
      - sum_CO2_abs_overall.png (2 painéis: car, bus)
      - mean_waitingTime_overall.png (3 painéis: person, car, bus)
      - satisfaction_index_overall.png (3 painéis: person, car, bus)
    """
    import os
    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt

    ensure_dir(overall_dir)

    # -------- carregar tudo --------
    data: Dict[str, Dict[str, Optional[pd.DataFrame]]] = {}
    for s in scenarios:
        kpis, acc = load_scenario_data(s)
        data[s.appendix] = {"kpis": kpis, "acc": acc}

    # ordem "bonita" para appendices (numérica quando possível)
    def _sort_key(x: str):
        sx = str(x)
        try:
            return float(sx)
        except ValueError:
            return sx

    appendices_sorted = sorted(data.keys(), key=_sort_key)

    # -------- helper: construir pivot de satisfaction agregado (car + bus) --------
    def build_satisfaction_pivot_car_bus() -> Optional[pd.DataFrame]:
        frames = []
        for appendix in appendices_sorted:
            kpis = data[appendix]["kpis"]
            if kpis is None:
                continue
            needed = {"day", "mode", "mean_duration", "mean_CO2_abs"}
            if not needed.issubset(set(kpis.columns)):
                continue

            # soma (por dia) de car + bus
            car = kpi_filter_mode(kpis, "car")[["day", "mean_effectiveTime", "mean_CO2_abs"]].rename(
                columns={"mean_effectiveTime": "mean_duration_car", "mean_CO2_abs": "mean_CO2_abs_car"}
            )
            bus = kpi_filter_mode(kpis, "bus")[["day", "mean_effectiveTime", "mean_CO2_abs"]].rename(
                columns={"mean_effectiveTime": "mean_duration_bus", "mean_CO2_abs": "mean_CO2_abs_bus"}
            )

            if car.empty and bus.empty:
                continue

            tmp = pd.merge(car, bus, on="day", how="outer")
            tmp[[
                "mean_duration_car",
                "mean_duration_bus",
                "mean_CO2_abs_car",
                "mean_CO2_abs_bus",
            ]] = tmp[[
                "mean_duration_car",
                "mean_duration_bus",
                "mean_CO2_abs_car",
                "mean_CO2_abs_bus",
            ]].fillna(0)

            tmp["KPI"] = 0.7 * (
                tmp["mean_duration_car"] + tmp["mean_duration_bus"]
            ) + 0.3 * (tmp["mean_CO2_abs_car"] + tmp["mean_CO2_abs_bus"])

            tmp = tmp[["day", "KPI"]]
            tmp["appendix"] = appendix
            frames.append(tmp)

        if not frames:
            return None

        all_df = pd.concat(frames, ignore_index=True)
        pivot = all_df.pivot_table(index="day", columns="appendix", values="KPI", aggfunc="mean")
        return pivot


    # -----------------------------
    # 4) Satisfaction index (agregado: car + bus)
    # -----------------------------
    pivot = build_satisfaction_pivot_car_bus()

    fig, ax = plt.subplots(1, 1, figsize=(10, 3.6), sharex=True)
    if pivot is None:
        ax.set_title(f"KPI (overall) — {map_name}")
        ax.grid(True, axis="y", alpha=0.3)
    else:
        plot_grouped_bars_from_pivot(
            ax=ax,
            pivot=pivot,
            ylabel="KPI",
            title="User Preferences - Bus Lane Types",
            show_legend=True,
        )

    ax.set_xlabel("Day")

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(overall_dir, "kpi_overall.png"), dpi=200)
    plt.close(fig)



# -----------------------------
# Main driver
# -----------------------------

def build_scenarios(
    runs_dir: str,
    map_names: List[str],
    appendices: List[str],
    variants_new: List[str],
    variants: List[str],
) -> List[Scenario]:
    """Build list of scenario folders that exist.

    Folder pattern (ordem):
      map_name + variant_new + variant_old + appendix

    Exemplos:
      - {map}_{appendix}                                  (quando ambas são base)
      - {map}_{variant_new}_{appendix}                    (quando variant_old é base)
      - {map}_{variant_old}_{appendix}                    (quando variant_new é base)
      - {map}_{variant_new}_{variant_old}_{appendix}      (caso geral)

    Nota: para evitar duplicados, se variants já contiver variantes_new, elas são removidas de variants.
    """
    scenarios: List[Scenario] = []

    def norm(v) -> str:
        if v is None:
            return "base"
        v = str(v).strip()
        return "base" if v in ("", "base") else v

    variants_new_norm = [norm(v) for v in variants_new]
    variants_old_norm = [norm(v) for v in variants if norm(v) not in set(variants_new_norm)]

    for m in map_names:
        for a in appendices:
            for vnew in variants_new_norm:
                for vold in variants_old_norm:
                    parts = [m]
                    if vnew != "base":
                        parts.append(vnew)
                    if vold != "base":
                        parts.append(vold)
                    parts.append(str(a))

                    folder = "_".join(parts)
                    path = os.path.join(runs_dir, folder)

                    if os.path.isdir(path):
                        scenarios.append(Scenario(map_name=m, appendix=str(a), folder_name=folder, path=path))
                    else:
                        print(f"[WARN] Cenário não encontrado (a saltar): {path}")

    return scenarios



def run(
    fase_dir: str,
    map_names: List[str],
    appendices: List[str],
    variants_new: List[str],
    variants: List[str],
    runs_folder_name: str = "_sumo_runs_",
    plots_folder_name: str = "plots",
) -> None:
    runs_dir = os.path.join(fase_dir, runs_folder_name)
    if not os.path.isdir(runs_dir):
        raise FileNotFoundError(f"Não encontrei a pasta de runs: {runs_dir}")

    plots_dir = os.path.join(fase_dir, plots_folder_name)
    ensure_dir(plots_dir)

    scenarios = build_scenarios(runs_dir, map_names, appendices, variants_new, variants)

    # Overall (por map + appendix): compara variantes
    overall_root = os.path.join(plots_dir, "overall")
    ensure_dir(overall_root)

    def norm(v) -> str:
        if v is None:
            return "base"
        v = str(v).strip()
        return "base" if v in ("", "base") else v

    variants_new_norm = [norm(v) for v in variants_new]
    variants_old_norm = [norm(v) for v in variants if norm(v) not in set(variants_new_norm)]

    for a in appendices:
        for vold in variants_old_norm:
            group: List[Scenario] = []

            for m in map_names:
                for vnew in variants_new_norm:
                    parts = [m]
                    if vnew != "base":
                        parts.append(vnew)
                    if vold != "base":
                        parts.append(vold)
                    parts.append(str(a))

                    folder = "_".join(parts)
                    found = next((s for s in scenarios if s.folder_name == folder), None)
                    if found is None:
                        continue

                    # label das colunas: map + variant_new (para não colidir se tiveres vários mapas)
                    label = f"{m}_{vnew}" if vnew != "base" else f"{m}_base"
                    group.append(Scenario(map_name=m, appendix=label, folder_name=found.folder_name, path=found.path))

            # precisa de pelo menos 2 para comparar
            if len(group) < 2:
                continue

            group_name = f"{vold}_{a}" if vold != "base" else f"base_{a}"
            out_dir = os.path.join(overall_root, group_name)
            print(f"[INFO] Overall: {group_name} ({', '.join([g.appendix for g in group])}) -> {out_dir}")
            make_overall_plots_bars(group_name, group, out_dir)

    print("[DONE] Plots gerados com sucesso.")



if __name__ == "__main__":
    # ---- EDITA AQUI conforme o teu caso ----
    # Exemplo:
    #   fase_dir = "Fase_0"
    #   map_names = ["baseline", "grid"]
    #   appendices = ["1000", "10000", "25000"]
    #
    fase_dir = ""   # Para quem rodar dentro do vs usar -> "Fase_0"
    map_names = ["grid"]
    variants_new = ["", "bus_lines", "bus_stops"]
    variants = ["UserPreference_Baseline", "UserPreference_Time", "UserPreference_Cost", "UserPreference_CO2"]
    appendices = ["10000"]

    run(fase_dir=fase_dir, map_names=map_names, appendices=appendices, variants_new=variants_new, variants=variants)
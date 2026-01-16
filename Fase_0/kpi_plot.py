#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from dataclasses import dataclass
from typing import List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# -----------------------------
# Helpers
# -----------------------------

@dataclass(frozen=True)
class Scenario:
    map_name: str
    appendix: str
    folder_name: str
    path: str


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_read_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV não encontrado: {path}")
    return pd.read_csv(path)


def build_scenarios(runs_dir: str, map_names: List[str], appendices: List[str]) -> List[Scenario]:
    scenarios: List[Scenario] = []
    for m in map_names:
        for a in appendices:
            folder = f"{m}_{a}"
            path = os.path.join(runs_dir, folder)
            if os.path.isdir(path):
                scenarios.append(Scenario(map_name=m, appendix=str(a), folder_name=folder, path=path))
            else:
                print(f"[WARN] Cenário não encontrado (a saltar): {path}")
    return scenarios


def sort_appendices(appendices: List[str]) -> List[str]:
    def _k(x: str):
        try:
            return float(str(x))
        except ValueError:
            return str(x)
    return sorted([str(a) for a in appendices], key=_k)


def kpi_filter_mode(kpis: pd.DataFrame, mode: str) -> pd.DataFrame:
    out = kpis[kpis["mode"] == mode].copy()
    out = out.sort_values(["day"])
    return out


# -----------------------------
# Only plot: KPI (overall) as GROUPED BARS
# -----------------------------

def make_overall_kpi_bars(map_name: str, scenarios: List[Scenario], out_dir: str) -> None:
    """
    Gera APENAS 1 gráfico (barras agrupadas) por map_name:
      - KPI_overall.png

    KPI por dia e por appendix:
      KPI = 0.7*(mean_duration_car + mean_duration_bus) + 0.3*(sum_CO2_abs_car + sum_CO2_abs_bus)
    """
    ensure_dir(out_dir)

    frames = []

    for s in scenarios:
        kpi_path = os.path.join(s.path, "summary_daily_kpis.csv")
        kpis = safe_read_csv(kpi_path)

        needed = {"day", "mode", "mean_effectiveTime", "sum_CO2_abs"}
        if not needed.issubset(set(kpis.columns)):
            missing = sorted(list(needed - set(kpis.columns)))
            raise ValueError(f"[{s.folder_name}] Faltam colunas em {kpi_path}: {missing}")

        car = kpi_filter_mode(kpis, "car")[["day", "mean_effectiveTime", "sum_CO2_abs"]].rename(
            columns={"mean_effectiveTime": "mean_duration_car", "sum_CO2_abs": "sum_CO2_abs_car"}
        )
        bus = kpi_filter_mode(kpis, "bus")[["day", "mean_effectiveTime", "sum_CO2_abs"]].rename(
            columns={"mean_effectiveTime": "mean_duration_bus", "sum_CO2_abs": "sum_CO2_abs_bus"}
        )

        # merge por day para somar car + bus
        merged = pd.merge(car, bus, on="day", how="outer").sort_values("day")

        # se algum dia não tiver car/bus, fica NaN; aqui assumimos 0 para não “matar” o KPI
        merged[[
            "mean_duration_car", "mean_duration_bus",
            "sum_CO2_abs_car", "sum_CO2_abs_bus"
        ]] = merged[[
            "mean_duration_car", "mean_duration_bus",
            "sum_CO2_abs_car", "sum_CO2_abs_bus"
        ]].fillna(0.0)

        merged["KPI"] = (
            0.7 * (merged["mean_duration_car"] + merged["mean_duration_bus"])
            + 0.3 * (merged["sum_CO2_abs_car"] + merged["sum_CO2_abs_bus"])
        )

        merged["appendix"] = s.appendix
        frames.append(merged[["day", "appendix", "KPI"]])

    if not frames:
        print(f"[WARN] Sem dados para KPI em {map_name}.")
        return

    all_df = pd.concat(frames, ignore_index=True)

    # pivot: index=day, columns=appendix, values=KPI
    pivot = all_df.pivot_table(index="day", columns="appendix", values="KPI", aggfunc="mean").sort_index()

    # ordenar colunas (appendices) “bonito”
    cols_sorted = [c for c in sort_appendices(list(pivot.columns)) if c in pivot.columns]
    pivot = pivot[cols_sorted]

    days = pivot.index.to_list()
    cols = list(pivot.columns)

    if len(days) == 0 or len(cols) == 0:
        print(f"[WARN] Pivot vazio para {map_name}.")
        return

    x = np.arange(len(days))
    n = len(cols)
    width = 0.8 / max(n, 1)

    fig, ax = plt.subplots(1, 1, figsize=(10, 4))

    for i, c in enumerate(cols):
        y = pivot[c].values
        ax.bar(x + (i - (n - 1) / 2) * width, y, width=width, label=str(c))

    ax.set_title(f"KPI (overall) — {map_name}")
    ax.set_xlabel("Day")
    ax.set_ylabel("KPI")
    ax.set_xticks(x)
    ax.set_xticklabels(days, rotation=45, ha="right")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="Number of Agents", ncol=min(3, len(cols)))

    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "KPI_overall.png"), dpi=200)
    plt.close(fig)


# -----------------------------
# Main
# -----------------------------

def run(
    fase_dir: str,
    map_names: List[str],
    appendices: List[str],
    runs_folder_name: str = "_sumo_runs_",
    plots_folder_name: str = "plots",
) -> None:
    runs_dir = os.path.join(fase_dir, runs_folder_name)
    if not os.path.isdir(runs_dir):
        raise FileNotFoundError(f"Não encontrei a pasta de runs: {runs_dir}")

    plots_dir = os.path.join(fase_dir, plots_folder_name)
    ensure_dir(plots_dir)

    scenarios = build_scenarios(runs_dir, map_names, appendices)

    overall_root = os.path.join(plots_dir, "overall")
    ensure_dir(overall_root)

    for m in map_names:
        group = [s for s in scenarios if s.map_name == m]
        if not group:
            print(f"[WARN] Sem cenários para map_name='{m}'.")
            continue

        out_dir = os.path.join(overall_root, m)
        print(f"[INFO] KPI (BARS): {m} -> {out_dir}")
        make_overall_kpi_bars(m, group, out_dir)

    print("[DONE] Gerado apenas o gráfico KPI (overall) com barras.")


if __name__ == "__main__":
    # ---- EDITA AQUI conforme o teu caso ----
    fase_dir = ""  # ex: "Fase_0"
    map_names = ["baseline", "grid"]
    appendices = ["1000", "10000", "25000"]

    run(fase_dir=fase_dir, map_names=map_names, appendices=appendices)

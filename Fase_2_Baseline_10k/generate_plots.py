#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import glob
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import matplotlib.pyplot as plt


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


def plot_line(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str,
    xlabel: str,
    ylabel: str,
    outpath: str,
    label: Optional[str] = None,
) -> None:
    fig = plt.figure()
    if label is None:
        plt.plot(df[x], df[y])
    else:
        plt.plot(df[x], df[y], label=label)
        plt.legend()
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    save_fig(fig, outpath)


def plot_multi_lines(
    series_list: List[Tuple[pd.Series, pd.Series, str]],
    title: str,
    xlabel: str,
    ylabel: str,
    outpath: str,
) -> None:
    """
    series_list: [(x_series, y_series, label), ...]
    """
    fig = plt.figure()
    for x_s, y_s, lab in series_list:
        plt.plot(x_s, y_s, label=lab)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.legend()
    save_fig(fig, outpath)


def plot_grouped_bars_from_pivot(
    pivot: pd.DataFrame,
    title: str,
    xlabel: str,
    ylabel: str,
    outpath: str,
) -> None:
    """
    pivot: index=day, columns=appendix labels, values=metric
    Faz barras agrupadas por dia.
    """
    pivot = pivot.sort_index()
    days = pivot.index.to_list()
    cols = list(pivot.columns)

    x = np.arange(len(days))
    n = max(len(cols), 1)
    width = 0.8 / n

    fig = plt.figure()

    for i, c in enumerate(cols):
        y = pivot[c].values
        plt.bar(x + (i - (n - 1) / 2) * width, y, width=width, label=str(c))

    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.xticks(x, days, rotation=45, ha="right")
    plt.legend()
    save_fig(fig, outpath)


def kpi_filter_mode(kpis: pd.DataFrame, mode: str) -> pd.DataFrame:
    out = kpis[kpis["mode"] == mode].copy()
    out = out.sort_values(["day"])
    return out


# -----------------------------
# Individual plots per scenario
# -----------------------------

def make_individual_plots(s: Scenario, out_dir: str) -> None:
    """
    Cria:
    - public_acceptance (acceptance_used vs day)
    - sum_CO2_abs carros vs autocarros
    - mean_waitingTime pessoas vs carros vs autocarros
    - satisfaction index (0.7*mean_duration + 0.3*mean_CO2_abs) pessoas/carros/bus
    """
    ensure_dir(out_dir)

    kpi_path = os.path.join(s.path, "summary_daily_kpis.csv")
    kpis = safe_read_csv(kpi_path)

    # ---- 1) public_acceptance ----
    acc_path = find_acceptance_csv(s.path)
    if acc_path is not None:
        acc = safe_read_csv(acc_path)
        # valida colunas mínimas
        for col in ["day", "acceptance_used"]:
            if col not in acc.columns:
                raise ValueError(f"[{s.folder_name}] Coluna '{col}' não existe em {acc_path}")

        acc = acc.sort_values("day")
        plot_line(
            acc,
            x="day",
            y="acceptance_used",
            title=f"Public Acceptance (acceptance_used) — {s.folder_name}",
            xlabel="Day",
            ylabel="acceptance_used",
            outpath=os.path.join(out_dir, "public_acceptance.png"),
        )
    else:
        print(f"[WARN] [{s.folder_name}] Não encontrei acceptance_log_*.csv; a saltar public_acceptance.")

    # ---- 2) sum_CO2_abs: car vs bus ----
    for col in ["day", "mode", "sum_CO2_abs"]:
        if col not in kpis.columns:
            raise ValueError(f"[{s.folder_name}] Coluna '{col}' não existe em {kpi_path}")

    car = kpi_filter_mode(kpis, "car")
    bus = kpi_filter_mode(kpis, "bus")

    series_list = []
    if not car.empty:
        series_list.append((car["day"], car["sum_CO2_abs"], "car"))
    if not bus.empty:
        series_list.append((bus["day"], bus["sum_CO2_abs"], "bus"))

    if series_list:
        plot_multi_lines(
            series_list,
            title=f"sum_CO2_abs — car vs bus — {s.folder_name}",
            xlabel="Day",
            ylabel="sum_CO2_abs",
            outpath=os.path.join(out_dir, "sum_CO2_abs_car_vs_bus.png"),
        )
    else:
        print(f"[WARN] [{s.folder_name}] Sem dados car/bus para sum_CO2_abs.")

    # ---- 3) mean_waitingTime: person vs car vs bus ----
    for col in ["mean_waitingTime"]:
        if col not in kpis.columns:
            raise ValueError(f"[{s.folder_name}] Coluna '{col}' não existe em {kpi_path}")

    person = kpi_filter_mode(kpis, "person")
    car = kpi_filter_mode(kpis, "car")
    bus = kpi_filter_mode(kpis, "bus")

    series_list = []
    if not person.empty:
        series_list.append((person["day"], person["mean_waitingTime"], "person"))
    if not car.empty:
        series_list.append((car["day"], car["mean_waitingTime"], "car"))
    if not bus.empty:
        series_list.append((bus["day"], bus["mean_waitingTime"], "bus"))

    if series_list:
        plot_multi_lines(
            series_list,
            title=f"Mean waiting time — person vs car vs bus — {s.folder_name}",
            xlabel="Day",
            ylabel="mean_waitingTime",
            outpath=os.path.join(out_dir, "mean_waitingTime_person_car_bus.png"),
        )
    else:
        print(f"[WARN] [{s.folder_name}] Sem dados person/car/bus para mean_waitingTime.")

    # ---- 4) satisfaction index (0.7*mean_duration + 0.3*mean_CO2_abs) ----
    for col in ["mean_duration", "mean_CO2_abs"]:
        if col not in kpis.columns:
            raise ValueError(f"[{s.folder_name}] Coluna '{col}' não existe em {kpi_path}")

    def add_si(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["satisfaction_index"] = 0.7 * out["mean_duration"] + 0.3 * out["mean_CO2_abs"]
        return out

    person_si = add_si(person) if not person.empty else person
    car_si = add_si(car) if not car.empty else car
    bus_si = add_si(bus) if not bus.empty else bus

    series_list = []
    if not person_si.empty:
        series_list.append((person_si["day"], person_si["satisfaction_index"], "person"))
    if not car_si.empty:
        series_list.append((car_si["day"], car_si["satisfaction_index"], "car"))
    if not bus_si.empty:
        series_list.append((bus_si["day"], bus_si["satisfaction_index"], "bus"))

    if series_list:
        plot_multi_lines(
            series_list,
            title=f"Satisfaction index (0.7*mean_duration + 0.3*mean_CO2_abs) — {s.folder_name}",
            xlabel="Day",
            ylabel="satisfaction_index",
            outpath=os.path.join(out_dir, "satisfaction_index_person_car_bus.png"),
        )
    else:
        print(f"[WARN] [{s.folder_name}] Sem dados para satisfaction index.")


# -----------------------------
# Overall plots per map_name
# -----------------------------

def load_scenario_data(s: Scenario) -> Tuple[pd.DataFrame, Optional[pd.DataFrame]]:
    kpis = safe_read_csv(os.path.join(s.path, "summary_daily_kpis.csv"))
    acc_path = find_acceptance_csv(s.path)
    acc = safe_read_csv(acc_path) if acc_path else None
    return kpis, acc


def make_overall_plots_lines(map_name: str, scenarios: List[Scenario], overall_dir: str) -> None:
    """
    Comparação "overall" dentro do mesmo map_name, entre appendices.
    Para legibilidade:
      - public_acceptance: 1 plot com linhas por appendix
      - sum_CO2_abs: 2 plots (car e bus), linhas por appendix
      - waiting time: 3 plots (person, car, bus), linhas por appendix
      - satisfaction index: 3 plots (person, car, bus), linhas por appendix
    """
    ensure_dir(overall_dir)

    # Carrega tudo
    data: Dict[str, Dict[str, Optional[pd.DataFrame]]] = {}
    for s in scenarios:
        kpis, acc = load_scenario_data(s)
        data[s.appendix] = {"kpis": kpis, "acc": acc}

    # ---- public_acceptance overall ----
    series_list = []
    for appendix, dct in data.items():
        acc = dct["acc"]
        if acc is None:
            continue
        if "day" in acc.columns and "acceptance_used" in acc.columns:
            acc = acc.sort_values("day")
            series_list.append((acc["day"], acc["acceptance_used"], f"{map_name}_{appendix}"))
    if series_list:
        plot_multi_lines(
            series_list,
            title=f"Public Acceptance (acceptance_used) — {map_name} (appendix comparison)",
            xlabel="Day",
            ylabel="acceptance_used",
            outpath=os.path.join(overall_dir, "public_acceptance_overall.png"),
        )

    # ---- sum_CO2_abs overall (car and bus separate) ----
    def overall_kpi_lines(mode: str, y_col: str, title: str, outname: str):
        lines = []
        for appendix, dct in data.items():
            kpis = dct["kpis"]
            if not {"day", "mode", y_col}.issubset(set(kpis.columns)):
                continue
            df = kpi_filter_mode(kpis, mode)
            if df.empty:
                continue
            lines.append((df["day"], df[y_col], f"{map_name}_{appendix}"))
        if lines:
            plot_multi_lines(
                lines,
                title=title,
                xlabel="Day",
                ylabel=y_col,
                outpath=os.path.join(overall_dir, outname),
            )

    overall_kpi_lines(
        mode="car",
        y_col="sum_CO2_abs",
        title=f"sum_CO2_abs — car — {map_name} (appendix comparison)",
        outname="sum_CO2_abs_car_overall.png",
    )
    overall_kpi_lines(
        mode="bus",
        y_col="sum_CO2_abs",
        title=f"sum_CO2_abs — bus — {map_name} (appendix comparison)",
        outname="sum_CO2_abs_bus_overall.png",
    )

    # ---- mean_waitingTime overall (person/car/bus) ----
    for mode in ["person", "car", "bus"]:
        overall_kpi_lines(
            mode=mode,
            y_col="mean_waitingTime",
            title=f"Mean waiting time — {mode} — {map_name} (appendix comparison)",
            outname=f"mean_waitingTime_{mode}_overall.png",
        )

    # ---- satisfaction index overall (person/car/bus) ----
    def overall_satisfaction(mode: str):
        lines = []
        for appendix, dct in data.items():
            kpis = dct["kpis"]
            needed = {"day", "mode", "mean_duration", "mean_CO2_abs"}
            if not needed.issubset(set(kpis.columns)):
                continue
            df = kpi_filter_mode(kpis, mode)
            if df.empty:
                continue
            df = df.sort_values("day").copy()
            df["satisfaction_index"] = 0.7 * df["mean_duration"] + 0.3 * df["mean_CO2_abs"]
            lines.append((df["day"], df["satisfaction_index"], f"{map_name}_{appendix}"))
        if lines:
            plot_multi_lines(
                lines,
                title=f"Satisfaction index — {mode} — {map_name} (appendix comparison)",
                xlabel="Day",
                ylabel="satisfaction_index",
                outpath=os.path.join(overall_dir, f"satisfaction_index_{mode}_overall.png"),
            )

    for mode in ["person", "car", "bus"]:
        overall_satisfaction(mode)


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

    # -------- helper: barras agrupadas a partir de pivot (index=day, cols=appendix) --------
    def plot_grouped_bars_from_pivot(
        ax,
        pivot: pd.DataFrame,
        ylabel: str,
        title: str,
        show_legend: bool = True,
    ) -> None:
        pivot = pivot.sort_index()
        days = pivot.index.to_list()
        cols = [c for c in appendices_sorted if c in pivot.columns]

        if len(days) == 0 or len(cols) == 0:
            ax.set_title(title + " (no data)")
            return

        x = np.arange(len(days))
        n = len(cols)
        width = 0.8 / max(n, 1)

        for i, c in enumerate(cols):
            y = pivot[c].values
            ax.bar(x + (i - (n - 1) / 2) * width, y, width=width, label=str(c))

        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3)

        ax.set_xticks(x)
        ax.set_xticklabels(days, rotation=45, ha="right")

        if show_legend:
            ax.legend(title="appendix", ncol=min(3, len(cols)))

    # -------- helper: construir pivot de KPI por modo --------
    def build_kpi_pivot(mode: str, value_col: str) -> Optional[pd.DataFrame]:
        frames = []
        for appendix in appendices_sorted:
            kpis = data[appendix]["kpis"]
            if kpis is None:
                continue
            if not {"day", "mode", value_col}.issubset(set(kpis.columns)):
                continue
            dfm = kpi_filter_mode(kpis, mode)
            if dfm.empty:
                continue
            tmp = dfm[["day", value_col]].copy()
            tmp["appendix"] = appendix
            frames.append(tmp)

        if not frames:
            return None

        all_df = pd.concat(frames, ignore_index=True)
        pivot = all_df.pivot_table(index="day", columns="appendix", values=value_col, aggfunc="mean")
        return pivot

    # -------- helper: construir pivot de satisfaction por modo --------
    def build_satisfaction_pivot(mode: str) -> Optional[pd.DataFrame]:
        frames = []
        for appendix in appendices_sorted:
            kpis = data[appendix]["kpis"]
            if kpis is None:
                continue
            needed = {"day", "mode", "mean_duration", "mean_CO2_abs"}
            if not needed.issubset(set(kpis.columns)):
                continue
            dfm = kpi_filter_mode(kpis, mode)
            if dfm.empty:
                continue
            tmp = dfm[["day", "mean_duration", "mean_CO2_abs"]].copy()
            tmp["satisfaction_index"] = 0.7 * tmp["mean_duration"] + 0.3 * tmp["mean_CO2_abs"]
            tmp = tmp[["day", "satisfaction_index"]]
            tmp["appendix"] = appendix
            frames.append(tmp)

        if not frames:
            return None

        all_df = pd.concat(frames, ignore_index=True)
        pivot = all_df.pivot_table(index="day", columns="appendix", values="satisfaction_index", aggfunc="mean")
        return pivot

    # -----------------------------
    # 1) Acceptance (1 painel)
    # -----------------------------
    acc_frames = []
    for appendix in appendices_sorted:
        acc = data[appendix]["acc"]
        if acc is None:
            continue
        if not {"day", "acceptance_used"}.issubset(set(acc.columns)):
            continue
        tmp = acc[["day", "acceptance_used"]].copy()
        tmp["appendix"] = appendix
        acc_frames.append(tmp)

    if acc_frames:
        acc_all = pd.concat(acc_frames, ignore_index=True)
        pivot = acc_all.pivot_table(index="day", columns="appendix", values="acceptance_used", aggfunc="mean")

        fig, ax = plt.subplots(1, 1, figsize=(10, 4))
        plot_grouped_bars_from_pivot(
            ax=ax,
            pivot=pivot,
            ylabel="acceptance_used",
            title=f"Public Acceptance (acceptance_used) — {map_name}",
            show_legend=True,
        )
        fig.tight_layout()
        fig.savefig(os.path.join(overall_dir, "public_acceptance_overall.png"), dpi=200)
        plt.close(fig)

    # -----------------------------
    # 2) sum_CO2_abs (2 painéis: car, bus)
    # -----------------------------
    modes = ["car", "bus"]
    pivots = [build_kpi_pivot(m, "sum_CO2_abs") for m in modes]

    fig, axes = plt.subplots(len(modes), 1, figsize=(10, 3.2 * len(modes)), sharex=True)
    if len(modes) == 1:
        axes = [axes]

    for ax, mode, pivot in zip(axes, modes, pivots):
        if pivot is None:
            ax.set_title(f"{mode} (no data)")
            ax.grid(True, axis="y", alpha=0.3)
            continue
        plot_grouped_bars_from_pivot(
            ax=ax,
            pivot=pivot,
            ylabel="sum_CO2_abs",
            title=mode,
            show_legend=True,
        )

    axes[-1].set_xlabel("Day")
    fig.suptitle(f"sum_CO2_abs — {map_name} (appendix comparison)", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(overall_dir, "sum_CO2_abs_overall.png"), dpi=200)
    plt.close(fig)

    # -----------------------------
    # 3) mean_waitingTime (3 painéis: person, car, bus)
    # -----------------------------
    modes = ["person", "car", "bus"]
    pivots = [build_kpi_pivot(m, "mean_waitingTime") for m in modes]

    fig, axes = plt.subplots(len(modes), 1, figsize=(10, 3.2 * len(modes)), sharex=True)
    if len(modes) == 1:
        axes = [axes]

    for ax, mode, pivot in zip(axes, modes, pivots):
        if pivot is None:
            ax.set_title(f"{mode} (no data)")
            ax.grid(True, axis="y", alpha=0.3)
            continue
        plot_grouped_bars_from_pivot(
            ax=ax,
            pivot=pivot,
            ylabel="mean_waitingTime",
            title=mode,
            show_legend=True,
        )

    axes[-1].set_xlabel("Day")
    fig.suptitle(f"Mean waiting time — {map_name} (appendix comparison)", y=0.99)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(overall_dir, "mean_waitingTime_overall.png"), dpi=200)
    plt.close(fig)

    # -----------------------------
    # 4) Satisfaction index (3 painéis: person, car, bus)
    # -----------------------------
    modes = ["person", "car", "bus"]
    pivots = [build_satisfaction_pivot(m) for m in modes]

    fig, axes = plt.subplots(len(modes), 1, figsize=(10, 3.2 * len(modes)), sharex=True)
    if len(modes) == 1:
        axes = [axes]

    for ax, mode, pivot in zip(axes, modes, pivots):
        if pivot is None:
            ax.set_title(f"{mode} (no data)")
            ax.grid(True, axis="y", alpha=0.3)
            continue
        plot_grouped_bars_from_pivot(
            ax=ax,
            pivot=pivot,
            ylabel="satisfaction_index",
            title=mode,
            show_legend=True,
        )

    axes[-1].set_xlabel("Day")
    fig.suptitle(
        f"Satisfaction index (0.7*mean_duration + 0.3*mean_CO2_abs) — {map_name} (appendix comparison)",
        y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(overall_dir, "satisfaction_index_overall.png"), dpi=200)
    plt.close(fig)



# -----------------------------
# Main driver
# -----------------------------

def build_scenarios(
    runs_dir: str,
    map_names: List[str],
    appendices: List[str],
    variants: List[str],
) -> List[Scenario]:
    """Build list of scenario folders that exist.

    Folder pattern:
      - base: {map}_{appendix}           when variant == "" or "base"
      - variant: {map}_{variant}_{appendix} otherwise
    """
    scenarios: List[Scenario] = []

    for m in map_names:
        for a in appendices:
            for v in variants:
                v_norm = "base" if v is None else str(v)
                if v_norm in ("", "base"):
                    folder = f"{m}_{a}"
                else:
                    folder = f"{m}_{v_norm}_{a}"

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
    variants: List[str],
    runs_folder_name: str = "_sumo_runs_",
    plots_folder_name: str = "plots",
) -> None:
    runs_dir = os.path.join(fase_dir, runs_folder_name)
    if not os.path.isdir(runs_dir):
        raise FileNotFoundError(f"Não encontrei a pasta de runs: {runs_dir}")

    plots_dir = os.path.join(fase_dir, plots_folder_name)
    ensure_dir(plots_dir)

    scenarios = build_scenarios(runs_dir, map_names, appendices, variants)

    # Individuais
    for s in scenarios:
        out_dir = os.path.join(plots_dir, s.folder_name)
        print(f"[INFO] Individuais: {s.folder_name} -> {out_dir}")
        make_individual_plots(s, out_dir)

    # Overall (por map + appendix): compara variantes
    overall_root = os.path.join(plots_dir, "overall")
    ensure_dir(overall_root)

    for m in map_names:
        for a in appendices:
            group: List[Scenario] = []

            for v in variants:
                v_norm = "base" if v is None else str(v)
                if v_norm in ("", "base"):
                    folder = f"{m}_{a}"
                    label = "base"
                else:
                    folder = f"{m}_{v_norm}_{a}"
                    label = v_norm

                found = next((s for s in scenarios if s.folder_name == folder), None)
                if found is None:
                    continue

                # Importante: aqui "appendix" passa a ser o label da variante,
                # porque o make_overall_plots_bars usa s.appendix para as colunas das barras
                group.append(Scenario(map_name=m, appendix=label, folder_name=found.folder_name, path=found.path))

            # precisa de pelo menos 2 para comparar
            if len(group) < 2:
                continue

            group_name = f"{m}_{a}"
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
    variants = ["UserPreference_Baseline", "UserPreference_Time", "UserPreference_Cost", "UserPreference_CO2"]
    appendices = ["10000"]

    run(fase_dir=fase_dir, map_names=map_names, appendices=appendices, variants=variants)

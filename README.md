# TrafficCongestionPoliciesAffet-SimulationAndModelling
This project was developed for the "Modelling and Simulation" course and aims to compare how different policies to alleviate traffic congestion affects the choice and the impact of using private vehicles and public transports. First Semester of the First Year of the Masters's Degree in Artificial Intelligence at FEUP/FCUP.

This repository contains Python scripts and modules to automate, simulate, and analyze the effects of various traffic congestion policies using SUMO (Simulation of Urban MObility). The workspace is organized into several phases and scenarios, each with its own simulation and plotting scripts.

## Requirements

- **Python 3.8+**
- **SUMO** (Simulation of Urban MObility) installed and available in your PATH

### Python Packages

Install the required Python packages using:

```sh
pip install matplotlib pandas numpy
```

Other dependencies may be required depending on your scenario. Check the import statements in each script for additional packages.

## Folder Structure

- `Fase_0/`, `Fase_1_Bus_Lanes/`, `Fase_1_Number_of_Buses/`, `Fase_2_Baseline/`, etc.: Each folder contains scripts for a specific phase/scenario.
- Top-level scripts: General utilities and automation scripts.

## How to Run Simulations

### 1. Prepare SUMO Network Files

Each scenario folder (e.g., `baseline_map`, `grid_map`) must contain the necessary SUMO network files:
- `.net.xml` (network)
- `.rou.xml` (routes)
- `.add.xml` (additional elements like bus stops)

### 2. Run Simulation Automation

Navigate to the desired phase folder (e.g., `Fase_2_Baseline`) and run the automation script:

```sh
python automate_simulations.py
```

- Edit the variables at the top of the script (e.g., `MAP_TYPE`, `POLICY_TYPE`, `PEOPLE_GLOBAL`) to configure your simulation.
- The results will be saved in the `_sumo_runs_` folder inside the phase directory.

### 3. Clean and Aggregate Results

If needed, use the provided utilities (e.g., `csvCleaner`) to process raw SUMO outputs.

### 4. Generate Plots and KPIs

After running simulations, generate plots and KPIs:

#### For Plots

```sh
python generate_plots.py
```

#### For KPI Plots

```sh
python kpi_plot.py
```

- Edit the variables at the bottom of each script (e.g., `fase_dir`, `map_names`, `appendices`, `variants`) to match your scenario.
- Plots will be saved in the `plots` folder inside the phase directory.

### 5. Example Workflow

```sh
cd Fase_2_Baseline
python automate_simulations.py
python generate_plots.py
python kpi_plot.py
```

## Notes

- Always check and edit the configuration variables in each script before running.
- If running inside Visual Studio Code, set the working directory accordingly and use the integrated terminal for commands.
- Output folders (`_sumo_runs_`, `plots`) are created automatically if they do not exist.

## Troubleshooting

- If you get a `FileNotFoundError` for runs or plots folders, ensure you have run the simulation step and that the folder paths are correct.
- SUMO must be installed and accessible from your command line.

## Contact

For questions or issues, please open an issue in this repository.

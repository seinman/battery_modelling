# Electronic Union — Battery Storage Investment Model

Welcome to the Electronic Union - an alliance of five states with historically distinct approaches to electricity generation: Coalland, the Gaseous Isles, Windtopia, the Solar Peninsula and the Nuclear Republic.

The Federal Energy Authority of the Electronic Union is considering how to unify the countries' electricity grids in the face of rising CO2e prices.

It has two weapons at its disposal: building new connections between the member states, and building additional storage capacity. In order to understand what its best options are, the FEA's developers have built a dashboard using PyPSA to explore how total cost varies with infrastructure decisions and carbon price. 

---

## Quick Start

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

This installs the `electronic_union` package in editable mode plus Jupyter for the demo notebook. Omit `[dev]` if you only need the dashboard.

### 2. Pre-compute tieline scenarios

This runs 64 investment optimisations (all combinations of 6 potential interconnectors) and saves results to `data/scenarios.parquet`. **Takes ~12 minutes** on a standard laptop.

```bash
python scripts/precompute.py
```

### 3. Explore the demo notebook

```bash
jupyter notebook notebooks/demo.ipynb
```

The notebook walks through: network structure → synthetic time series → battery dispatch mechanics → tieline scenario results.

### 4. Launch the dashboard

```bash
streamlit run app/main.py
```

#### Or run in Docker

The Docker image bakes in the pre-computed scenarios, so the reviewer does not need to run the precompute step.

**Prerequisites:**

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Install the Compose plugin: `brew install docker-compose`
3. Open Docker Desktop and wait for the whale icon in the menu bar to stop animating before running any `docker` commands

```bash
docker-compose up --build
```

Then open [http://localhost:8501](http://localhost:8501).

> **Note:** `data/scenarios.parquet` must exist before running `docker build`
> (i.e. run step 2 first). The file is gitignored but is copied into the image.

---

## Project Structure

```
electronic_union/       Core model package
  constants.py          Shared constants (SNAPSHOT_WEIGHT, AVERAGE_LOADS, …)
  network.py            Static network: buses, generators, battery sites
  timeseries.py         Synthetic wind/solar/load time series generator
  tielines.py           Potential interconnectors and helper to activate them
  plots.py              Matplotlib visualisation functions

scripts/
  precompute.py         Runs all 64 tieline scenarios → data/scenarios.parquet

notebooks/
  demo.ipynb            End-to-end walkthrough (requires precomputed results)

app/                    [TODO] Streamlit dashboard
data/                   Generated outputs (gitignored)
```

---

## Model Design

### Five fictional countries

| Country | Primary resource | Role in the system |
|---|---|---|
| Windtopia | Onshore wind (1 400 MW) | High-latitude, variable; expensive gas backup |
| Gaseous Isles | Gas CCGT + peaker | Flexible mid-merit supply |
| Coalland | Coal (1 800 MW) | Cheap but high-carbon baseload |
| Solar Peninsula | Large PV (2 000 MW) + peaker | High solar but no overnight supply without storage |
| Nuclear Republic | Nuclear (1 800 MW) | Reliable baseload, high capital cost |

Battery sites are extendable at all five countries; the optimiser decides how much to build at each.

### Representative weeks

Rather than a full 8 760-hour year, the model uses **four representative weeks** — one per season, each 168 hours. Each snapshot is weighted by 13 (≈ 13 real weeks per representative week) so that annualised costs and dispatch volumes scale correctly. This keeps optimisation fast while preserving the seasonal structure that drives storage value.

### Battery economics

Batteries are modelled as 6-hour StorageUnits (round-trip efficiency 81%). Capital costs vary by site to reflect grid connection quality and civil works. The Solar Peninsula uses expensive open-cycle peaker backup (reflecting a diesel/LNG-dependent isolated peninsula), which is the main driver of storage value there.

All `capital_cost` values in the model are **annualised** (€/MW/year), not overnight costs. The optimiser compares annualised capex directly against annual operational savings — batteries are not assumed to last one year. The annualisation uses a 7% discount rate; the implied overnight costs are broadly consistent with a 10–15 year asset lifetime for grid-scale Li-ion storage. [TODO: pin down a specific lifetime assumption if deriving costs from first principles.]

### Tieline scenarios vs carbon price

The 64 tieline scenarios are **pre-computed** because each requires a full re-solve and the parameter space is discrete and bounded. The carbon price slider in the dashboard is handled as a **live re-solve**: it only shifts generator marginal costs, which is fast enough (< 5 s per solve) to run interactively without pre-computation.

---

## Limitations

- Transmission is modelled as lossless DC links (no AC power flow)
- All parameters are fictional, calibrated loosely on North-West European climatology
- Demand response, hydro, and hydrogen are not modelled

---

## Further development

- Sensitivity analysis (battery cost trajectories, demand growth)
- AC load flow / network constraints

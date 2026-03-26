# Electronic Union — Battery Storage Investment Model

[TODO: one-paragraph description of the project for the job application context]

A PyPSA-based power system model for a fictional five-country union, built to explore how transmission interconnection affects optimal battery storage investment. The optimiser (HiGHS via Linopy) sizes battery capacity at each candidate site to minimise total annual system cost across all countries.

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

[TODO: once built]

```bash
streamlit run app/main.py
```

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
- [TODO: anything else worth flagging]

---

## [TODO] Further development

- Docker / reproducibility instructions
- Sensitivity analysis (battery cost trajectories, demand growth)
- AC load flow / network constraints

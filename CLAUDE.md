# CLAUDE.md — Electronic Union project notes

Guidance for future Claude Code sessions on this project.

---

## What this project is

A PyPSA investment optimisation model for a fictional five-country power system ("Electronic Union"). The main deliverable is a Streamlit dashboard showing how battery storage investment changes across all 64 combinations of 6 potential transmission tielines.

The project is a job application take-home. Code quality and design clarity matter as much as correctness.

---

## Package layout

```
electronic_union/
  constants.py    — SNAPSHOT_WEIGHT=13, HOURS_PER_WEEK=168, AVERAGE_LOADS dict
  network.py      — build_network(): buses, generators (fixed), battery sites (extendable)
  timeseries.py   — make_snapshots(), attach_timeseries(): synthetic wind/solar/load
  tielines.py     — POTENTIAL_TIELINES list, add_tielines(n, names)
  plots.py        — plot_wind, plot_solar, plot_loads, plot_wind_solar_overlay,
                    plot_battery_dispatch
scripts/
  precompute.py   — all 64 tieline scenarios → data/scenarios.parquet (~12 min)
notebooks/
  demo.ipynb      — narrative walkthrough; Section 4 requires precomputed parquet
app/              — Streamlit dashboard (not yet built)
data/             — generated outputs, gitignored
```

---

## Key design decisions

**Snapshot weighting**
- `snapshot_weightings["generators"]` and `["objective"]` = 13 (scales annual costs correctly)
- `snapshot_weightings["stores"]` = 1.0 (must be physical hours between snapshots — do not change)

**Battery parameters**
- `max_hours=6`, `efficiency_store=0.9`, `efficiency_dispatch=0.9`
- `cyclic_state_of_charge=False`, `state_of_charge_initial=0` — each representative week balances independently (setting cyclic=True would allow unphysical cross-week energy transfer)

**Solar Peninsula backup**
- `marginal_cost=2600 €/MWh` — deliberately high, representing a diesel/LNG-dependent isolated peninsula with no pipeline gas. This is what makes batteries economic there. Do not reduce this to a realistic CCGT cost without understanding the knock-on effect on battery investment.

**Carbon price**
- Not pre-computed. The Streamlit slider re-solves live by adjusting `n.generators.marginal_cost` for coal/gas/CCGT carriers. Fast enough (< 5 s) to run interactively.

**Tieline scenarios**
- 2^6 = 64 combinations pre-computed in `scripts/precompute.py`
- Results stored per-scenario: battery MW per site, total MW per country, system cost, dispatch by carrier, mean LMP per bus

---

## Things to be careful about

- **Never mutate a network between optimizer runs.** Always build fresh with `build_network()` + `attach_timeseries()`. Reusing a network object causes shape-mismatch errors in PyPSA post-processing.
- **`attach_timeseries` always advances the RNG through all 4 seasons** in fixed order, even if only a subset of seasons is active. This preserves per-season profiles when `seed=42` regardless of which seasons are included. Don't refactor this without understanding the seed consistency logic.
- The `countries` parameter on `build_network()` filters buses/generators/loads/batteries to a subset. Useful for quick debugging runs but not the default.

---

## Still to build

- [ ] Streamlit app (`app/main.py`) — tieline checkboxes + carbon price slider + key charts
- [ ] `pyproject.toml` ✅
- [ ] `.gitignore`
- [ ] Docker / reproducibility setup

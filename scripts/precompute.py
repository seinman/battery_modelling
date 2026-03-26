"""
Pre-compute all 2^6 = 64 tieline scenarios for the Electronic Union network.

For each scenario we run a full investment optimisation and extract:
  - which tielines are active
  - number of active tielines
  - optimised battery capacity per site (MW)
  - total battery capacity per country (MW)
  - total system cost (€/year)
  - dispatch energy (MWh_el / year) and cost (€/year) per carrier
  - mean LMP (€/MWh) per country

Output: data/scenarios.parquet

Usage:
    python scripts/precompute.py
    python scripts/precompute.py --output path/to/output.parquet
"""

import sys
import itertools
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import logging
logging.getLogger("linopy").setLevel(logging.WARNING)
logging.getLogger("pypsa").setLevel(logging.WARNING)

# Allow running from repo root without installing the package
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from electronic_union import (
    build_network,
    make_snapshots,
    attach_timeseries,
    POTENTIAL_TIELINES,
    add_tielines,
)

try:
    from tqdm import tqdm
    HAVE_TQDM = True
except ImportError:
    HAVE_TQDM = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_and_solve(tieline_names: list[str]) -> dict:
    """Build network, attach time series, add tielines, optimise. Return dict."""
    snapshots = make_snapshots()
    n = build_network(snapshots=snapshots)
    attach_timeseries(n, seed=42)
    add_tielines(n, tieline_names)
    n.optimize(
        solver_name="highs",
        output_flag=False,
        include_objective_constant=False,
        progress=False,
    )

    row: dict = {}

    # --- tieline metadata ---
    row["tielines"] = "|".join(tieline_names) if tieline_names else "(none)"
    row["n_tielines"] = len(tieline_names)
    for tl in POTENTIAL_TIELINES:
        row[f"tl_{tl['name']}"] = tl["name"] in tieline_names

    # --- total system cost ---
    row["total_cost_eur"] = float(n.objective)

    # --- battery capacities ---
    batteries = n.storage_units[n.storage_units.p_nom_extendable]
    for _, su in batteries.iterrows():
        row[f"bat_{su.name}"] = float(su.p_nom_opt)

    # total per country
    for country in ["Windtopia", "Gaseous Isles", "Coalland",
                    "Solar Peninsula", "Nuclear Republic"]:
        mask = batteries.bus == country
        row[f"bat_total_{country}"] = float(batteries.loc[mask, "p_nom_opt"].sum())

    # --- dispatch per carrier ---
    weight = n.snapshot_weightings["generators"]
    for carrier in n.carriers.index:
        gens = n.generators[n.generators.carrier == carrier]
        if gens.empty:
            continue
        dispatch_cols = [g for g in gens.index if g in n.generators_t.p.columns]
        if dispatch_cols:
            weighted = n.generators_t.p[dispatch_cols].multiply(weight, axis=0)
            energy_mwh = float(weighted.values.sum())
            mc_series = n.generators.loc[dispatch_cols, "marginal_cost"]
            cost_eur = float(weighted.multiply(mc_series, axis=1).values.sum())
        else:
            energy_mwh = 0.0
            cost_eur = 0.0
        row[f"dispatch_mwh_{carrier}"] = energy_mwh
        row[f"dispatch_cost_eur_{carrier}"] = cost_eur

    # --- battery dispatch (StorageUnits, not Generators — not in carrier loop above) ---
    if not n.storage_units_t.p_dispatch.empty:
        row["dispatch_mwh_battery"] = float(
            n.storage_units_t.p_dispatch.multiply(weight, axis=0).values.sum()
        )
    else:
        row["dispatch_mwh_battery"] = 0.0
    row["dispatch_cost_eur_battery"] = 0.0   # batteries have no marginal cost

    # --- mean LMP per country ---
    if hasattr(n, "buses_t") and "marginal_price" in n.buses_t.__dict__:
        for bus in n.buses.index:
            if bus in n.buses_t.marginal_price.columns:
                row[f"lmp_{bus}"] = float(n.buses_t.marginal_price[bus].mean())
            else:
                row[f"lmp_{bus}"] = np.nan
    else:
        for bus in n.buses.index:
            row[f"lmp_{bus}"] = np.nan

    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pre-compute EU tieline scenarios.")
    parser.add_argument(
        "--output", default="data/scenarios.parquet",
        help="Output parquet path (default: data/scenarios.parquet)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip scenarios already present in the output file.",
    )
    parser.add_argument(
        "--max-scenarios", type=int, default=None, metavar="N",
        help="Stop after N scenarios (useful for quick debugging runs).",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tieline_names = [tl["name"] for tl in POTENTIAL_TIELINES]
    combos = list(itertools.product([False, True], repeat=len(tieline_names)))

    # Load existing results if resuming
    REQUIRED_COLS = {"total_cost_eur", "dispatch_mwh_wind", "dispatch_mwh_solar"}
    existing_keys: set[str] = set()
    rows: list[dict] = []
    if args.resume and output_path.exists():
        existing = pd.read_parquet(output_path)
        missing = REQUIRED_COLS - set(existing.columns)
        if missing:
            print(f"WARNING: existing file is missing columns {missing} — "
                  f"ignoring it and starting fresh.")
        else:
            rows = existing.to_dict("records")
            existing_keys = set(existing["tielines"])
            print(f"Resuming — {len(existing_keys)} scenarios already done, "
                  f"{len(combos) - len(existing_keys)} remaining …")
    if not existing_keys:
        print(f"Running {len(combos)} scenarios …")

    todo = [
        flags for flags in combos
        if ("|".join(n for n, f in zip(tieline_names, flags) if f) or "(none)")
        not in existing_keys
    ]
    if args.max_scenarios is not None:
        todo = todo[:args.max_scenarios]
        print(f"(--max-scenarios {args.max_scenarios}: running {len(todo)} scenarios)")

    iterator = tqdm(todo, desc="Scenarios") if HAVE_TQDM else todo

    for flags in iterator:
        active = [name for name, flag in zip(tieline_names, flags) if flag]
        try:
            row = _build_and_solve(active)
        except Exception as exc:
            print(f"\n  WARNING: scenario {active} failed — {exc}", flush=True)
            row = {"tielines": "|".join(active) if active else "(none)",
                   "n_tielines": len(active),
                   "total_cost_eur": np.nan}
        rows.append(row)
        # Save after every scenario so progress survives a crash
        pd.DataFrame(rows).to_parquet(output_path, index=False)

    df = pd.DataFrame(rows)
    df.to_parquet(output_path, index=False)
    print(f"\nSaved {len(df)} rows → {output_path}")


if __name__ == "__main__":
    main()

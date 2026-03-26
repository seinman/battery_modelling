"""
Electronic Union — Streamlit dashboard.

Usage:
    streamlit run app/main.py
"""

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

# Allow running from repo root without the package being installed
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

logging.getLogger("pypsa").setLevel(logging.WARNING)
logging.getLogger("linopy").setLevel(logging.WARNING)

from electronic_union import (
    build_network,
    make_snapshots,
    attach_timeseries,
    add_tielines,
    POTENTIAL_TIELINES,
)
from electronic_union.network import BATTERY_SITES
from electronic_union.plots import COUNTRY_COLOURS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COUNTRIES = [
    "Windtopia", "Gaseous Isles", "Coalland", "Solar Peninsula", "Nuclear Republic"
]

CARRIER_COLOURS = {
    "wind":     "#4C72B0",
    "solar":    "#E8A217",
    "nuclear":  "#8172B2",
    "gas":      "#DD8452",
    "gas_ocgt": "#E05C5C",
    "coal":     "#777777",
    "battery":  "#2CA02C",
}

CARRIER_LABELS = {
    "wind": "Wind", "solar": "Solar", "nuclear": "Nuclear",
    "gas": "Gas (CCGT)", "gas_ocgt": "Gas (OCGT)", "coal": "Coal",
    "battery": "Battery",
}

CO2_FACTORS = {"coal": 0.85, "gas": 0.35, "gas_ocgt": 0.55}

# Tielines are treated as 40-year assets at 7% discount rate
# annuity = r / (1 - (1+r)^-n)
_r, _n = 0.07, 40
TIELINE_ANNUITY = _r / (1 - (1 + _r) ** -_n)   # ≈ 0.0750

PARQUET_PATH = repo_root / "data" / "scenarios.parquet"

# ---------------------------------------------------------------------------
# Cached data / solve functions
# ---------------------------------------------------------------------------

@st.cache_data
def load_scenarios() -> pd.DataFrame:
    return pd.read_parquet(PARQUET_PATH)


@st.cache_data(show_spinner=False)
def run_scenario(tieline_names: tuple[str, ...], carbon_price: float) -> dict:
    """Build, adjust costs, optimise, and return a serialisable results dict."""
    snapshots = make_snapshots()
    n = build_network(snapshots=snapshots)
    attach_timeseries(n, seed=42)
    add_tielines(n, list(tieline_names))

    # Store base marginal costs before adding carbon, so we can separate
    # fuel costs from carbon costs in the breakdown
    base_mc = n.generators["marginal_cost"].copy()

    for carrier, factor in CO2_FACTORS.items():
        mask = n.generators.carrier == carrier
        n.generators.loc[mask, "marginal_cost"] += carbon_price * factor

    n.optimize(
        solver_name="highs",
        output_flag=False,
        include_objective_constant=False,
        progress=False,
    )

    weight = n.snapshot_weightings["generators"]

    battery_by_country = {
        c: float(n.storage_units.loc[n.storage_units.bus == c, "p_nom_opt"].sum())
        for c in COUNTRIES
    }

    battery_capex_eur = float(
        (n.storage_units["p_nom_opt"] * n.storage_units["capital_cost"]).sum()
    )

    dispatch_by_carrier: dict[str, float] = {}
    fuel_cost_by_carrier: dict[str, float] = {}
    carbon_cost_by_carrier: dict[str, float] = {}

    for carrier in CARRIER_COLOURS:
        if carrier == "battery":
            if not n.storage_units_t.p_dispatch.empty:
                dispatch_by_carrier["battery"] = float(
                    n.storage_units_t.p_dispatch.multiply(weight, axis=0).values.sum()
                )
        else:
            gens = n.generators[n.generators.carrier == carrier]
            cols = [g for g in gens.index if g in n.generators_t.p.columns]
            if cols:
                mwh = float(
                    n.generators_t.p[cols].multiply(weight, axis=0).values.sum()
                )
                if mwh > 0:
                    dispatch_by_carrier[carrier] = mwh
                    fuel_cost_by_carrier[carrier] = float(
                        n.generators_t.p[cols]
                        .multiply(weight, axis=0)
                        .multiply(base_mc.loc[cols], axis=1)
                        .values.sum()
                    )
                    co2 = CO2_FACTORS.get(carrier, 0.0)
                    if co2 > 0:
                        carbon_cost_by_carrier[carrier] = mwh * co2 * carbon_price

    battery_by_site = {
        su.name: float(su.p_nom_opt)
        for _, su in n.storage_units.iterrows()
    }

    return {
        "total_cost_eur": float(n.objective),
        "battery_capex_eur": battery_capex_eur,
        "battery_by_country": battery_by_country,
        "battery_by_site": battery_by_site,
        "dispatch_by_carrier": dispatch_by_carrier,
        "fuel_cost_by_carrier": fuel_cost_by_carrier,
        "carbon_cost_by_carrier": carbon_cost_by_carrier,
    }


def _results_from_parquet(row: pd.Series) -> dict:
    """Unpack a parquet row into the same structure as run_scenario()."""
    dispatch_by_carrier: dict[str, float] = {}
    fuel_cost_by_carrier: dict[str, float] = {}

    for carrier in CARRIER_COLOURS:
        mwh_col  = f"dispatch_mwh_{carrier}"
        cost_col = f"dispatch_cost_eur_{carrier}"
        if mwh_col in row.index and not pd.isna(row[mwh_col]) and row[mwh_col] > 0:
            dispatch_by_carrier[carrier] = float(row[mwh_col])
        if cost_col in row.index and not pd.isna(row[cost_col]) and row[cost_col] > 0:
            fuel_cost_by_carrier[carrier] = float(row[cost_col])

    battery_by_site = {
        site["name"]: float(row[f"bat_{site['name']}"])
        for site in BATTERY_SITES
        if f"bat_{site['name']}" in row.index
    }
    battery_capex_eur = sum(
        battery_by_site.get(s["name"], 0.0) * s["capital_cost"]
        for s in BATTERY_SITES
    )

    return {
        "total_cost_eur": float(row["total_cost_eur"]),
        "battery_capex_eur": battery_capex_eur,
        "battery_by_country": {c: float(row[f"bat_total_{c}"]) for c in COUNTRIES},
        "battery_by_site": battery_by_site,
        "dispatch_by_carrier": dispatch_by_carrier,
        "fuel_cost_by_carrier": fuel_cost_by_carrier,
        "carbon_cost_by_carrier": {},   # carbon_price = 0 for parquet path
    }


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------

def _battery_chart(battery_by_country: dict) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(5, 3.5))
    countries = list(battery_by_country.keys())
    values = [battery_by_country[c] for c in countries]
    colours = [COUNTRY_COLOURS[c] for c in countries]

    bars = ax.barh(countries, values, color=colours, edgecolor="white", height=0.6)
    ax.bar_label(bars, fmt="{:.0f} MW", padding=4, fontsize=8)

    max_val = max(values) if max(values) > 0 else 100
    ax.set_xlim(0, max_val * 1.28)
    ax.set_xlabel("Optimised capacity (MW)")
    ax.set_title("Battery investment by country", fontweight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig


def _dispatch_chart(dispatch_by_carrier: dict) -> plt.Figure:
    fig, ax = plt.subplots(figsize=(5, 3.5))
    carriers = [c for c in CARRIER_COLOURS if c in dispatch_by_carrier]
    values = [dispatch_by_carrier[c] / 1e6 for c in carriers]  # → TWh
    colours = [CARRIER_COLOURS[c] for c in carriers]
    labels = [CARRIER_LABELS[c] for c in carriers]

    bars = ax.bar(labels, values, color=colours, edgecolor="white", width=0.6)
    ax.bar_label(bars, fmt="{:.2f}", padding=2, fontsize=8)

    ax.set_ylabel("Annual dispatch (TWh)")
    ax.set_title("Generation mix", fontweight="bold")
    ax.tick_params(axis="x", rotation=20)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Electronic Union",
    layout="wide",
    page_icon="⚡",
)

st.title("Electronic Union — Battery Storage Investment")
st.caption(
    "Explore how transmission interconnection and carbon pricing affect optimal "
    "battery storage investment across five fictional countries. "
    "Select tielines and a carbon price in the sidebar to update results."
)

if not PARQUET_PATH.exists():
    st.error(
        "Pre-computed scenarios not found. "
        "Run `python scripts/precompute.py` from the repo root first."
    )
    st.stop()

# --- sidebar ---
with st.sidebar:
    st.header("Tieline Configuration")
    selected_tielines: list[str] = []
    for tl in POTENTIAL_TIELINES:
        label = f"{tl['name']}  (€{tl['build_cost_meur']:.0f}M)"
        if st.checkbox(label, key=f"tl_{tl['name']}"):
            selected_tielines.append(tl["name"])

    total_build_cost_meur = sum(
        tl["build_cost_meur"] for tl in POTENTIAL_TIELINES
        if tl["name"] in selected_tielines
    )
    if selected_tielines:
        annualised_tieline_meur = total_build_cost_meur * TIELINE_ANNUITY
        st.caption(
            f"Overnight build cost: €{total_build_cost_meur:.0f}M  \n"
            f"Annualised (7%, 40 yr): €{annualised_tieline_meur:.1f}M/yr"
        )

    st.divider()
    st.header("Carbon Price")
    carbon_price = st.slider("€/tCO₂", 0, 150, 0, step=5)
    if carbon_price > 0:
        st.caption("Live re-solve required (~15 s).")

# --- load or solve ---
tieline_key = "|".join(selected_tielines) if selected_tielines else "(none)"
df_all = load_scenarios()
baseline_cost = float(df_all.loc[df_all["tielines"] == "(none)", "total_cost_eur"].iloc[0])

results: dict
if carbon_price == 0:
    row = df_all.loc[df_all["tielines"] == tieline_key].iloc[0]
    results = _results_from_parquet(row)
else:
    with st.spinner("Solving optimisation…"):
        results = run_scenario(tuple(selected_tielines), float(carbon_price))

# --- headline metrics ---
system_cost_saving_meur = (baseline_cost - results["total_cost_eur"]) / 1e6
annualised_tieline_meur = total_build_cost_meur * TIELINE_ANNUITY
net_saving_meur = system_cost_saving_meur - annualised_tieline_meur
total_battery = sum(results["battery_by_country"].values())

dispatch = results.get("dispatch_by_carrier", {})
total_co2_mt = sum(
    dispatch.get(carrier, 0.0) * factor / 1e6
    for carrier, factor in CO2_FACTORS.items()
)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Annual system cost", f"€{results['total_cost_eur'] / 1e9:.2f}B")
m2.metric(
    "System cost saving",
    f"€{system_cost_saving_meur:.0f}M/yr",
    help="Reduction in optimised system cost (battery capex + running costs) vs the "
         "no-tielines, zero-carbon-price baseline. Does not include tieline build cost.",
)
m3.metric(
    "Net saving (incl. tieline build)",
    f"€{net_saving_meur:.0f}M/yr",
    help="System cost saving minus annualised tieline capital cost (7% discount rate, 40-year life).",
)
m4.metric("Total battery capacity", f"{total_battery:.0f} MW")
m5.metric("Total CO₂ emissions", f"{total_co2_mt:.1f} Mt/yr")

# --- charts ---
c1, c2 = st.columns(2)

with c1:
    st.pyplot(_battery_chart(results["battery_by_country"]), use_container_width=True)
with c2:
    if results["dispatch_by_carrier"]:
        st.pyplot(_dispatch_chart(results["dispatch_by_carrier"]), use_container_width=True)
    else:
        st.info(
            "Generation mix not available — re-run `scripts/precompute.py` "
            "to regenerate the scenarios file with dispatch data."
        )

# --- battery site table ---
st.subheader("Battery sites")

battery_by_site = results.get("battery_by_site", {})
bat_rows = []
for site in BATTERY_SITES:
    name = site["name"]
    p_nom_opt = battery_by_site.get(name, 0.0)
    bat_rows.append({
        "Site": name,
        "Country": site["bus"],
        "Capex (€/MW/yr)": site["capital_cost"],
        "Duration (h)": 6,
        "Built (MW)": p_nom_opt,
        "Energy capacity (MWh)": p_nom_opt * 6,
        "Annual capex (€M/yr)": p_nom_opt * site["capital_cost"] / 1e6,
    })

built_table = (
    pd.DataFrame(bat_rows)
    .loc[lambda d: d["Built (MW)"] > 0.1]
    .reset_index(drop=True)
)

if built_table.empty:
    st.caption("No batteries built in this scenario.")
else:
    st.dataframe(
        built_table.style.format({
            "Capex (€/MW/yr)": "€{:,.0f}",
            "Built (MW)": "{:.1f}",
            "Energy capacity (MWh)": "{:.0f}",
            "Annual capex (€M/yr)": "{:.1f}",
        }),
        use_container_width=True,
        hide_index=True,
    )



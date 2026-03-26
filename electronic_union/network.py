"""
Electronic Union — base network definition.

All costs are annualised at 7% discount rate over asset lifetime.
Power units: MW. Cost units: €/MW/year (generators) or €/MWh-capacity/year (batteries).

Generators are fixed (existing plant). Batteries are extendable — the optimiser
decides how much capacity to build at each site.

Time series (variable capacity factors for wind/solar, load profiles) are handled
separately. This module builds the static skeleton.
"""

import pypsa
import pandas as pd

from .constants import AVERAGE_LOADS


# ---------------------------------------------------------------------------
# Carriers  (co2_emissions in tCO2/MWh_el)
# ---------------------------------------------------------------------------

CARRIERS = {
    "AC":      {"co2_emissions": 0.0},   # bus carrier
    "wind":    {"co2_emissions": 0.0},
    "solar":   {"co2_emissions": 0.0},
    "nuclear": {"co2_emissions": 0.0},
    "gas":     {"co2_emissions": 0.35},  # CCGT ~55% efficiency
    "gas_ocgt":{"co2_emissions": 0.55},  # open-cycle peaker / backup
    "coal":    {"co2_emissions": 0.85},
    "battery": {"co2_emissions": 0.0},
}


# ---------------------------------------------------------------------------
# Buses
# ---------------------------------------------------------------------------

BUSES = {
    #                         x (lon-like)  y (lat-like)
    "Windtopia":         {"x":  0,  "y":  5},
    "Gaseous Isles":     {"x": -3,  "y":  2},
    "Coalland":          {"x":  3,  "y":  2},
    "Nuclear Republic":  {"x": -2,  "y":  0},
    "Solar Peninsula":   {"x":  2,  "y":  0},
}


# ---------------------------------------------------------------------------
# Generators  (existing, fixed capacity)
# ---------------------------------------------------------------------------
# capital_cost here is for reference / cost accounting only (not optimised).
# marginal_cost is €/MWh dispatched.

GENERATORS = [
    # --- Windtopia: two onshore wind farms + open-cycle gas backup ---
    # Backup runs only when wind is insufficient; high cost creates strong
    # incentive for batteries to reduce its use.
    dict(name="Windtopia Wind 1",       bus="Windtopia",        carrier="wind",
         p_nom=800,  marginal_cost=0,   capital_cost=102_000),
    dict(name="Windtopia Wind 2",       bus="Windtopia",        carrier="wind",
         p_nom=600,  marginal_cost=0,   capital_cost=102_000),
    # Windtopia is an isolated northern island with no pipeline gas;
    # backup power is expensive imported LNG / diesel.
    dict(name="Windtopia Backup",       bus="Windtopia",        carrier="gas_ocgt",
         p_nom=1_200, marginal_cost=350, capital_cost=45_000),

    # --- Gaseous Isles: two CCGTs + one open-cycle peaker ---
    dict(name="Gaseous CCGT 1",         bus="Gaseous Isles",    carrier="gas",
         p_nom=500,  marginal_cost=65,  capital_cost=68_000),
    dict(name="Gaseous CCGT 2",         bus="Gaseous Isles",    carrier="gas",
         p_nom=400,  marginal_cost=68,  capital_cost=68_000),
    dict(name="Gaseous Peaker",         bus="Gaseous Isles",    carrier="gas_ocgt",
         p_nom=200,  marginal_cost=95,  capital_cost=45_000),

    # --- Coalland: three coal plants (different ages → different costs) ---
    dict(name="Coalland Plant 1",       bus="Coalland",         carrier="coal",
         p_nom=700,  marginal_cost=44,  capital_cost=110_000),
    dict(name="Coalland Plant 2",       bus="Coalland",         carrier="coal",
         p_nom=700,  marginal_cost=48,  capital_cost=110_000),
    dict(name="Coalland Plant 3",       bus="Coalland",         carrier="coal",
         p_nom=400,  marginal_cost=55,  capital_cost=110_000),

    # --- Solar Peninsula: two large PV parks + gas backup for nights ---
    dict(name="Solar PV 1",             bus="Solar Peninsula",  carrier="solar",
         p_nom=1_200, marginal_cost=0,  capital_cost=51_000),
    dict(name="Solar PV 2",             bus="Solar Peninsula",  carrier="solar",
         p_nom=800,  marginal_cost=0,   capital_cost=51_000),
    # Solar Peninsula has pipeline gas but relies on expensive open-cycle peakers
    # for nighttime backup — high fuel cost reflects peaker economics.
    dict(name="Solar Peninsula Backup", bus="Solar Peninsula",  carrier="gas_ocgt",
         p_nom=1_500, marginal_cost=260, capital_cost=45_000),

    # --- Nuclear Republic: two baseload nuclear units ---
    dict(name="Nuclear Unit 1",         bus="Nuclear Republic", carrier="nuclear",
         p_nom=1_000, marginal_cost=12, capital_cost=433_000),
    dict(name="Nuclear Unit 2",         bus="Nuclear Republic", carrier="nuclear",
         p_nom=800,  marginal_cost=14,  capital_cost=433_000),
]


# ---------------------------------------------------------------------------
# Battery sites  (extendable — optimiser sizes these)
# ---------------------------------------------------------------------------
# capital_cost: annualised €/MW of power capacity/year, for a 6-hour battery.
# Sites near cheap grid connection or brownfield land have lower costs.

BATTERY_SITES = [
    # Windtopia: good grid connection next to wind farms
    dict(name="Windtopia Battery A",        bus="Windtopia",        capital_cost=85_000),
    dict(name="Windtopia Battery B",        bus="Windtopia",        capital_cost=112_000),

    # Gaseous Isles: island terrain, difficult civil works
    dict(name="Gaseous Isles Battery A",    bus="Gaseous Isles",    capital_cost=122_000),
    dict(name="Gaseous Isles Battery B",    bus="Gaseous Isles",    capital_cost=145_000),
    dict(name="Gaseous Isles Battery C",    bus="Gaseous Isles",    capital_cost=165_000),

    # Coalland: disused industrial sites, very cheap
    dict(name="Coalland Battery A",         bus="Coalland",         capital_cost=72_000),
    dict(name="Coalland Battery B",         bus="Coalland",         capital_cost=88_000),

    # Solar Peninsula: co-located with PV parks, cheapest overall
    dict(name="Solar Peninsula Battery A",  bus="Solar Peninsula",  capital_cost=68_000),
    dict(name="Solar Peninsula Battery B",  bus="Solar Peninsula",  capital_cost=92_000),
    dict(name="Solar Peninsula Battery C",  bus="Solar Peninsula",  capital_cost=118_000),

    # Nuclear Republic: regulatory overhead inflates costs
    dict(name="Nuclear Republic Battery A", bus="Nuclear Republic", capital_cost=132_000),
    dict(name="Nuclear Republic Battery B", bus="Nuclear Republic", capital_cost=155_000),
]


# ---------------------------------------------------------------------------
# Network builder
# ---------------------------------------------------------------------------

def build_network(
    snapshots: pd.DatetimeIndex | None = None,
    countries: list[str] | None = None,
) -> pypsa.Network:
    """
    Build and return the base Electronic Union network.

    Parameters
    ----------
    snapshots:
        Time index for the network. Defaults to one year of hourly snapshots.
        Pass a shorter index for fast test runs.
    countries:
        Subset of country names to include. Defaults to all five countries.
        Useful for isolated debugging: build_network(snapshots, countries=["Solar Peninsula"]).

    Returns
    -------
    pypsa.Network
        Configured network with buses, generators, loads, and extendable
        battery storage units. No tie lines — call add_tielines() separately.
    """
    if snapshots is None:
        snapshots = pd.date_range("2025-01-01", periods=8_760, freq="h")

    active_countries = set(countries) if countries is not None else set(BUSES)

    n = pypsa.Network()
    n.set_snapshots(snapshots)

    # Carriers (must be registered before components that reference them)
    for carrier, attrs in CARRIERS.items():
        n.add("Carrier", carrier, **attrs)

    # Buses
    for name, coords in BUSES.items():
        if name in active_countries:
            n.add("Bus", name, carrier="AC", x=coords["x"], y=coords["y"])

    # Generators (fixed capacity, not extendable)
    for g in GENERATORS:
        if g["bus"] not in active_countries:
            continue
        n.add("Generator", g["name"],
              bus=g["bus"],
              carrier=g["carrier"],
              p_nom=g["p_nom"],
              p_nom_extendable=False,
              marginal_cost=g["marginal_cost"],
              capital_cost=g["capital_cost"])

    # Loads (constant placeholder — overwrite p_set with a time series later)
    for country, p_set in AVERAGE_LOADS.items():
        if country in active_countries:
            n.add("Load", f"{country} Load", bus=country, p_set=p_set)

    # Battery sites (extendable — optimiser decides p_nom)
    for site in BATTERY_SITES:
        if site["bus"] not in active_countries:
            continue
        n.add("StorageUnit", site["name"],
              bus=site["bus"],
              carrier="battery",
              p_nom=0,
              p_nom_extendable=True,
              capital_cost=site["capital_cost"],
              max_hours=6,
              efficiency_store=0.9,
              efficiency_dispatch=0.9,
              # False: each representative week balances independently.
              # cyclic=True would let the battery pre-charge in one week and
              # discharge in a later non-contiguous week, which is unphysical.
              cyclic_state_of_charge=False,
              state_of_charge_initial=0)

    return n
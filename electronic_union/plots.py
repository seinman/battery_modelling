"""
Visualisation helpers for the Electronic Union network.

All functions take a fully-configured pypsa.Network (snapshots attached)
and return a matplotlib Figure so callers can save or display as needed.
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pypsa

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEASON_ORDER  = ["winter", "spring", "summer", "autumn"]
SEASON_TITLES = {
    "winter": "Winter  (w/c 13 Jan)",
    "spring": "Spring  (w/c 14 Apr)",
    "summer": "Summer  (w/c 14 Jul)",
    "autumn": "Autumn  (w/c 13 Oct)",
}

COUNTRY_COLOURS = {
    "Windtopia":        "#4C72B0",
    "Gaseous Isles":    "#DD8452",
    "Coalland":         "#55A868",
    "Solar Peninsula":  "#C44E52",
    "Nuclear Republic": "#8172B2",
}

WIND_COLOUR  = "#4C72B0"
SOLAR_COLOUR = "#E8A217"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _season_index(n: pypsa.Network, season_idx: int):
    """DatetimeIndex for season i (0=winter … 3=autumn)."""
    return n.snapshots[season_idx * 168 : (season_idx + 1) * 168]


def _fmt_xaxis(ax, idx):
    """Format x-axis as day-of-week labels with vertical midnight gridlines."""
    ax.set_xlim(idx[0], idx[-1])
    ax.xaxis.set_major_locator(mdates.DayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%a"))
    ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[6, 12, 18]))
    ax.tick_params(axis="x", which="major", labelsize=8)
    ax.grid(axis="x", which="major", color="0.80", linewidth=0.8)
    ax.grid(axis="x", which="minor", color="0.92", linewidth=0.5)
    ax.grid(axis="y", color="0.88", linewidth=0.6)


def _season_axes(fig_title: str):
    """Create a 2×2 figure with a shared style, return (fig, axes_flat)."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
    fig.suptitle(fig_title, fontsize=14, fontweight="bold")
    return fig, axes.flat


# ---------------------------------------------------------------------------
# Public plotting functions
# ---------------------------------------------------------------------------

def plot_wind(n: pypsa.Network) -> plt.Figure:
    """
    2×2 figure showing available wind generation (MW) for each season.

    Stacked area: Wind 1 on bottom, Wind 2 on top.
    Maximum available output = p_max_pu × p_nom.
    """
    wind_gens = n.generators[n.generators.carrier == "wind"].index.tolist()

    fig, axes = _season_axes("Available Wind Generation — Windtopia")

    for ax, (season_idx, season) in zip(axes, enumerate(SEASON_ORDER)):
        idx = _season_index(n, season_idx)

        # Stack generation from each unit
        bottom = np.zeros(168)
        alphas = [0.85, 0.55]
        for gen, alpha in zip(wind_gens, alphas):
            p_nom = n.generators.at[gen, "p_nom"]
            cf    = n.generators_t.p_max_pu[gen].loc[idx].values
            mw    = cf * p_nom
            ax.fill_between(idx, bottom, bottom + mw,
                            color=WIND_COLOUR, alpha=alpha,
                            label=gen)
            bottom = bottom + mw

        total_nom = sum(n.generators.at[g, "p_nom"] for g in wind_gens)
        ax.axhline(total_nom, color=WIND_COLOUR, linewidth=0.8,
                   linestyle="--", alpha=0.5, label=f"Installed ({total_nom:.0f} MW)")

        ax.set_title(SEASON_TITLES[season], fontsize=10)
        ax.set_ylabel("MW")
        ax.set_ylim(0, total_nom * 1.05)
        _fmt_xaxis(ax, idx)

    # Single legend beneath title
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3,
               fontsize=8, framealpha=0.9,
               bbox_to_anchor=(0.5, -0.02))
    return fig


def plot_solar(n: pypsa.Network) -> plt.Figure:
    """
    2×2 figure showing available solar generation (MW) for each season.

    Stacked area: PV 1 on bottom, PV 2 on top.
    """
    solar_gens = n.generators[n.generators.carrier == "solar"].index.tolist()

    fig, axes = _season_axes("Available Solar Generation — Solar Peninsula")

    for ax, (season_idx, season) in zip(axes, enumerate(SEASON_ORDER)):
        idx = _season_index(n, season_idx)

        bottom = np.zeros(168)
        alphas = [0.85, 0.55]
        for gen, alpha in zip(solar_gens, alphas):
            p_nom = n.generators.at[gen, "p_nom"]
            cf    = n.generators_t.p_max_pu[gen].loc[idx].values
            mw    = cf * p_nom
            ax.fill_between(idx, bottom, bottom + mw,
                            color=SOLAR_COLOUR, alpha=alpha,
                            label=gen)
            bottom = bottom + mw

        total_nom = sum(n.generators.at[g, "p_nom"] for g in solar_gens)
        ax.axhline(total_nom, color=SOLAR_COLOUR, linewidth=0.8,
                   linestyle="--", alpha=0.5, label=f"Installed ({total_nom:.0f} MW)")

        ax.set_title(SEASON_TITLES[season], fontsize=10)
        ax.set_ylabel("MW")
        ax.set_ylim(0, total_nom * 1.05)
        _fmt_xaxis(ax, idx)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3,
               fontsize=8, framealpha=0.9,
               bbox_to_anchor=(0.5, -0.02))
    return fig


def plot_loads(n: pypsa.Network) -> plt.Figure:
    """
    2×2 figure showing demand (MW) in all five countries for each season.

    One line per country, coloured by COUNTRY_COLOURS.
    """
    fig, axes = _season_axes("Weekly Load Profiles — All Countries")

    for ax, (season_idx, season) in zip(axes, enumerate(SEASON_ORDER)):
        idx = _season_index(n, season_idx)

        for load in n.loads.index:
            country = n.loads.at[load, "bus"]
            mw = n.loads_t.p_set[load].loc[idx].values
            ax.plot(idx, mw,
                    color=COUNTRY_COLOURS[country],
                    linewidth=1.2,
                    label=country)

        ax.set_title(SEASON_TITLES[season], fontsize=10)
        ax.set_ylabel("MW")
        _fmt_xaxis(ax, idx)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5,
               fontsize=8, framealpha=0.9,
               bbox_to_anchor=(0.5, -0.02))
    return fig


def plot_wind_solar_overlay(n: pypsa.Network) -> plt.Figure:
    """
    2×2 figure overlaying normalised wind CF (Windtopia) and solar CF
    (Solar Peninsula) to make the seasonal correlation pattern visible.
    """
    wind_gen  = n.generators[n.generators.carrier == "wind"].index[0]
    solar_gen = n.generators[n.generators.carrier == "solar"].index[0]

    fig, axes = _season_axes(
        "Wind vs Solar Capacity Factors — Seasonal Correlation"
    )

    for ax, (season_idx, season) in zip(axes, enumerate(SEASON_ORDER)):
        idx  = _season_index(n, season_idx)
        wind  = n.generators_t.p_max_pu[wind_gen].loc[idx].values
        solar = n.generators_t.p_max_pu[solar_gen].loc[idx].values

        # Daytime mask for correlation annotation
        mask = solar > 0.01
        corr = np.corrcoef(wind[mask], solar[mask])[0, 1] if mask.sum() > 5 else np.nan

        ax.fill_between(idx, wind,  color=WIND_COLOUR,  alpha=0.45, label="Wind CF (Windtopia)")
        ax.fill_between(idx, solar, color=SOLAR_COLOUR, alpha=0.55, label="Solar CF (Solar Peninsula)")
        ax.set_title(f"{SEASON_TITLES[season]}   [daytime corr = {corr:+.2f}]",
                     fontsize=9.5)
        ax.set_ylabel("Capacity factor")
        ax.set_ylim(0, 1.05)
        _fmt_xaxis(ax, idx)

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2,
               fontsize=9, framealpha=0.9,
               bbox_to_anchor=(0.5, -0.02))
    return fig


def plot_battery_dispatch(
    n: pypsa.Network,
    storage_unit: str | None = None,
    season_idx: int = 2,
) -> plt.Figure:
    """
    Two-panel figure for a single battery storage unit after optimisation.

    Top panel: stacked dispatch for the battery's local bus — charging
    (negative), discharging (positive), and any fossil backup.
    Bottom panel: state of charge (MWh).

    Parameters
    ----------
    n:
        Optimised network (n.optimize() already called).
    storage_unit:
        Name of the StorageUnit to inspect.  Defaults to the unit with the
        largest optimised p_nom on the network.
    season_idx:
        Which representative week to show (0=winter, 1=spring, 2=summer,
        3=autumn).  Defaults to summer (index 2).
    """
    # --- pick storage unit ---
    if storage_unit is None:
        built = n.storage_units[n.storage_units.p_nom_opt > 0]
        if built.empty:
            raise ValueError("No batteries were built in this optimisation.")
        storage_unit = built.p_nom_opt.idxmax()

    bus = n.storage_units.at[storage_unit, "bus"]
    idx = _season_index(n, season_idx)
    season_label = SEASON_ORDER[season_idx]

    # --- dispatch on this bus ---
    # generators on the same bus
    bus_gens = n.generators[n.generators.bus == bus].index

    # optimised generator output
    gen_dispatch = {}
    for g in bus_gens:
        carrier = n.generators.at[g, "carrier"]
        col = n.generators_t.p[g] if g in n.generators_t.p.columns else None
        if col is not None:
            gen_dispatch.setdefault(carrier, []).append(col.loc[idx].values)
        else:
            gen_dispatch.setdefault(carrier, []).append(np.zeros(168))

    # battery charge / discharge
    p_charge    = n.storage_units_t.p_store[storage_unit].loc[idx].values \
                  if storage_unit in n.storage_units_t.p_store.columns \
                  else np.zeros(168)
    p_discharge = n.storage_units_t.p_dispatch[storage_unit].loc[idx].values \
                  if storage_unit in n.storage_units_t.p_dispatch.columns \
                  else np.zeros(168)
    soc         = n.storage_units_t.state_of_charge[storage_unit].loc[idx].values \
                  if storage_unit in n.storage_units_t.state_of_charge.columns \
                  else np.zeros(168)

    # --- figure ---
    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(13, 7),
        gridspec_kw={"height_ratios": [2, 1]},
        constrained_layout=True,
    )
    fig.suptitle(
        f"Battery Dispatch — {storage_unit}  |  {SEASON_TITLES[season_label]}",
        fontsize=13, fontweight="bold",
    )

    CARRIER_COLOURS = {
        "wind":     WIND_COLOUR,
        "solar":    SOLAR_COLOUR,
        "nuclear":  "#8172B2",
        "gas":      "#DD8452",
        "gas_ocgt": "#E05C5C",
        "coal":     "#777777",
    }

    # Stacked positive supply
    bottom = np.zeros(168)
    for carrier, arrays in gen_dispatch.items():
        total = np.sum(arrays, axis=0)
        colour = CARRIER_COLOURS.get(carrier, "grey")
        ax_top.fill_between(idx, bottom, bottom + total,
                            color=colour, alpha=0.75, label=carrier)
        bottom = bottom + total

    # Battery discharge (positive)
    ax_top.fill_between(idx, bottom, bottom + p_discharge,
                        color="#2CA02C", alpha=0.80, label="Battery discharge")
    bottom = bottom + p_discharge

    # Battery charging as negative area
    ax_top.fill_between(idx, 0, -p_charge,
                        color="#2CA02C", alpha=0.35, label="Battery charging")

    # Load line
    load_name = f"{bus} Load"
    if load_name in n.loads.index and load_name in n.loads_t.p_set.columns:
        load = n.loads_t.p_set[load_name].loc[idx].values
        ax_top.plot(idx, load, color="black", linewidth=1.4,
                    linestyle="--", label="Load")

    ax_top.axhline(0, color="0.5", linewidth=0.6)
    ax_top.set_ylabel("MW")
    _fmt_xaxis(ax_top, idx)
    handles, labels = ax_top.get_legend_handles_labels()
    ax_top.legend(handles, labels, fontsize=8, loc="upper right",
                  framealpha=0.85, ncol=2)

    # State of charge
    p_nom_opt = n.storage_units.at[storage_unit, "p_nom_opt"]
    max_hours = n.storage_units.at[storage_unit, "max_hours"]
    max_soc   = p_nom_opt * max_hours
    ax_bot.fill_between(idx, soc, color="#2CA02C", alpha=0.45)
    ax_bot.plot(idx, soc, color="#2CA02C", linewidth=1.0)
    if max_soc > 0:
        ax_bot.axhline(max_soc, color="#2CA02C", linewidth=0.8,
                       linestyle="--", alpha=0.6,
                       label=f"Max SoC ({max_soc:.0f} MWh)")
    ax_bot.set_ylabel("State of Charge (MWh)")
    ax_bot.legend(fontsize=8, loc="upper right")
    _fmt_xaxis(ax_bot, idx)

    return fig
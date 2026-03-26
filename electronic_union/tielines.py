"""
Electronic Union — potential tie lines between countries.

Geography (see BUSES coordinates):

          Windtopia (0, 5)
         /              \\
  Gaseous Isles       Coalland
    (-3, 2)            (3, 2)
         \\              /
    Nuclear Republic  Solar Peninsula
        (-2, 0)          (2, 0)

Build costs are overnight capital in M€ (for dashboard display).
Transmission capacity is MW.

When a tie line is "built" it is added to the network as a fixed Link
(lossless DC approximation). AC losses can be added later.
"""

import pypsa
import math


# ---------------------------------------------------------------------------
# Potential tie lines
# ---------------------------------------------------------------------------

def _distance(b0: str, b1: str, buses: dict) -> float:
    """Euclidean distance between two buses (coordinate units → km via scale)."""
    KM_PER_UNIT = 150   # 1 coordinate unit ≈ 150 km
    dx = buses[b0]["x"] - buses[b1]["x"]
    dy = buses[b0]["y"] - buses[b1]["y"]
    return math.sqrt(dx**2 + dy**2) * KM_PER_UNIT


from .network import BUSES

_BUILD_COST_PER_KM = 1.5   # M€/km (overhead HVAC, 400 kV class)


def _tieline(name: str, bus0: str, bus1: str, p_nom: float = 500) -> dict:
    km = _distance(bus0, bus1, BUSES)
    return dict(
        name=name,
        bus0=bus0,
        bus1=bus1,
        p_nom=p_nom,            # MW
        length_km=round(km),
        build_cost_meur=round(km * _BUILD_COST_PER_KM, 1),
    )


POTENTIAL_TIELINES = [
    _tieline("Windtopia — Gaseous Isles",
             "Windtopia",       "Gaseous Isles"),

    _tieline("Windtopia — Coalland",
             "Windtopia",       "Coalland"),

    _tieline("Gaseous Isles — Nuclear Republic",
             "Gaseous Isles",   "Nuclear Republic"),

    _tieline("Coalland — Solar Peninsula",
             "Coalland",        "Solar Peninsula"),

    _tieline("Nuclear Republic — Solar Peninsula",
             "Nuclear Republic", "Solar Peninsula"),

    _tieline("Gaseous Isles — Coalland",
             "Gaseous Isles",   "Coalland",     p_nom=800),  # wider, more expensive route
]


# ---------------------------------------------------------------------------
# Helper to add selected tie lines to a network
# ---------------------------------------------------------------------------

def add_tielines(n: pypsa.Network, names: list[str]) -> pypsa.Network:
    """
    Add a subset of potential tie lines to the network.

    Parameters
    ----------
    n:
        The PyPSA network (modified in-place).
    names:
        List of tie-line names from POTENTIAL_TIELINES to activate.

    Returns
    -------
    pypsa.Network
        The same network object with links added.
    """
    lookup = {t["name"]: t for t in POTENTIAL_TIELINES}
    for name in names:
        if name not in lookup:
            raise ValueError(f"Unknown tie line: '{name}'. "
                             f"Options: {list(lookup)}")
        tl = lookup[name]
        n.add("Link", tl["name"],
              bus0=tl["bus0"],
              bus1=tl["bus1"],
              p_nom=tl["p_nom"],
              p_min_pu=-1,    # bidirectional
              efficiency=1.0)
    return n
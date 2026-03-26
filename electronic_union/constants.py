"""
Shared constants for the Electronic Union network.
"""

HOURS_PER_WEEK = 168
SNAPSHOT_WEIGHT = 13   # each representative hour stands for 13 real weeks

# Average annual loads (MW) — must match bus names in network.py
AVERAGE_LOADS = {
    "Windtopia":        700,
    "Gaseous Isles":    550,
    "Coalland":       1_100,
    "Solar Peninsula":  850,
    "Nuclear Republic": 950,
}

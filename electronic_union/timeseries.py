"""
Synthetic time series for the Electronic Union network.

Structure
---------
Four representative weeks (one per season), each 168 hours.
Every snapshot is weighted by 13 so that summed weights ≈ 1 year
(4 seasons × 168 h × 13 = 8 736 h).

Wind / solar correlation model
-------------------------------
A slow-moving "synoptic weather index" (AR-1, ~48 h autocorrelation)
represents the dominant pressure pattern for each season:

    +1  ≈ anticyclone  →  clear skies, calm winds
    -1  ≈ cyclone      →  cloud cover, strong winds

Solar output is positively correlated with the weather index
(clearer when anticyclonic). Wind output is negatively correlated.
This gives the physically motivated negative wind–solar correlation
that peaks in summer, when persistent high-pressure systems dominate.

Seasonal parameters are calibrated loosely on North-West European
climatology (Windtopia ≈ Scotland; Solar Peninsula ≈ Iberia).
"""

import numpy as np
import pandas as pd
import pypsa

from .constants import HOURS_PER_WEEK, SNAPSHOT_WEIGHT, AVERAGE_LOADS


# ---------------------------------------------------------------------------
# Season definitions
# ---------------------------------------------------------------------------

SEASONS: dict[str, dict] = {
    "winter": dict(
        week_start="2025-01-13",   # Monday 13 Jan
        day_of_year=15,
        weight=SNAPSHOT_WEIGHT,
        # Peak clear-sky capacity factor (noon, cloudless)
        solar_peak={"Windtopia": 0.08, "Solar Peninsula": 0.26},
        # Wind: mean and std of capacity factor
        wind_mean={"Windtopia": 0.52, "Solar Peninsula": 0.32},
        wind_std={"Windtopia": 0.18, "Solar Peninsula": 0.13},
        # How strongly weather index drives solar (+) and wind (-)
        solar_weather_corr=0.20,   # weak: winter sun is scarce regardless
        wind_weather_corr=-0.30,
        load_scale=1.15,           # winter demand is highest
        # Cloud transmission: fraction of clear-sky irradiance that reaches panels.
        # Low in winter (more cloud cover); higher latitude = cloudier.
        cloud_base=0.58,
        cloud_amp=0.18,
    ),
    "spring": dict(
        week_start="2025-04-14",
        day_of_year=104,
        weight=SNAPSHOT_WEIGHT,
        solar_peak={"Windtopia": 0.38, "Solar Peninsula": 0.65},
        wind_mean={"Windtopia": 0.43, "Solar Peninsula": 0.27},
        wind_std={"Windtopia": 0.17, "Solar Peninsula": 0.12},
        solar_weather_corr=0.45,
        wind_weather_corr=-0.45,
        load_scale=0.90,
        cloud_base=0.72,
        cloud_amp=0.15,
    ),
    "summer": dict(
        week_start="2025-07-14",
        day_of_year=195,
        weight=SNAPSHOT_WEIGHT,
        solar_peak={"Windtopia": 0.58, "Solar Peninsula": 0.90},
        wind_mean={"Windtopia": 0.30, "Solar Peninsula": 0.18},
        wind_std={"Windtopia": 0.12, "Solar Peninsula": 0.08},
        # Strongest correlation: persistent anticyclones = sunny + calm
        solar_weather_corr=0.65,
        wind_weather_corr=-0.60,
        load_scale=0.95,
        # High cloud_base: Solar Peninsula is Mediterranean — consistently sunny
        # in summer; day-to-day variability is low (mostly clear-sky days).
        cloud_base=0.85,
        cloud_amp=0.10,
    ),
    "autumn": dict(
        week_start="2025-10-13",
        day_of_year=286,
        weight=SNAPSHOT_WEIGHT,
        solar_peak={"Windtopia": 0.22, "Solar Peninsula": 0.47},
        wind_mean={"Windtopia": 0.47, "Solar Peninsula": 0.30},
        wind_std={"Windtopia": 0.19, "Solar Peninsula": 0.14},
        solar_weather_corr=0.35,
        wind_weather_corr=-0.40,
        load_scale=1.00,
        cloud_base=0.68,
        cloud_amp=0.15,
    ),
}

# Geographic latitude for solar geometry
LATITUDES = {
    "Windtopia": 58.0,       # ~Scotland / southern Scandinavia
    "Solar Peninsula": 36.0, # ~Iberia / southern Italy
}


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _synoptic_weather(rng: np.random.Generator) -> np.ndarray:
    """
    Daily synoptic weather index: 7 values, one per day of the week.

    Positive = anticyclone (clear / calm).
    Negative = cyclone (cloudy / windy).
    AR(1) with 2-day autocorrelation at daily resolution (alpha ≈ 0.61).

    Working at daily resolution keeps realized variance close to 1 over
    7 days, avoiding the variance blow-up that occurs with an hourly
    48-hour AR process evaluated over only one week.
    """
    alpha = np.exp(-1.0 / 2.0)   # 2-day timescale in units of days
    noise = rng.standard_normal(7)
    w = np.zeros(7)
    for d in range(1, 7):
        w[d] = alpha * w[d - 1] + np.sqrt(1.0 - alpha ** 2) * noise[d]
    return w   # unit variance


def _clear_sky_shape(day_of_year: int, latitude_deg: float) -> np.ndarray:
    """
    Normalised clear-sky solar shape for a 168-hour week.

    Uses the solar elevation angle (sin α) as a proxy for irradiance.
    The same day-of-year is repeated for all 7 days (intra-week day-length
    variation is negligible over one week).

    Returns values in [0, 1] where 1 = solar noon on the clearest day.
    """
    phi = np.radians(latitude_deg)
    delta = np.radians(23.45 * np.sin(2 * np.pi * (day_of_year - 81) / 365))

    elevations = np.zeros(HOURS_PER_WEEK)
    for h in range(HOURS_PER_WEEK):
        omega = np.radians((h % 24 - 12) * 15)   # hour angle
        sin_alpha = (np.sin(phi) * np.sin(delta)
                     + np.cos(phi) * np.cos(delta) * np.cos(omega))
        elevations[h] = max(0.0, float(sin_alpha))

    peak = elevations.max()
    return elevations / peak if peak > 0 else elevations


def _solar_cf(season: str,
              country: str,
              daily_weather: np.ndarray,
              rng: np.random.Generator) -> np.ndarray:
    """
    Hourly solar capacity factor for one week.

    clear-sky shape  ×  daily cloud transmission  ×  seasonal peak CF.

    Cloud transmission is set once per day from the daily weather index
    (anticyclone → clearer skies), plus small hourly residual noise.
    Working at daily resolution avoids variance blow-up from the slow
    weather AR process.
    """
    p = SEASONS[season]
    peak_cf = p["solar_peak"][country]
    corr = p["solar_weather_corr"]

    shape = _clear_sky_shape(p["day_of_year"], LATITUDES[country])

    cloud_base = p["cloud_base"]
    cloud_amp  = p["cloud_amp"]

    # One cloud-transmission value per day, modulated by weather
    daily_cloud = np.clip(
        cloud_base + cloud_amp * corr * daily_weather
        + 0.03 * rng.standard_normal(7),
        0.05, 1.0,
    )

    cf = np.zeros(HOURS_PER_WEEK)
    for t in range(HOURS_PER_WEEK):
        day_cloud = daily_cloud[t // 24]
        hourly_noise = 1.0 + 0.04 * rng.standard_normal()
        # peak_cf is the clear-sky maximum; multiply by cloud (≤1) to get actual output.
        cf[t] = shape[t] * day_cloud * hourly_noise * peak_cf

    return np.clip(cf, 0.0, 1.0)


def _wind_cf(season: str,
             country: str,
             daily_weather: np.ndarray,
             rng: np.random.Generator) -> np.ndarray:
    """
    Hourly wind capacity factor for one week.

    An Ornstein-Uhlenbeck process mean-reverts to a daily target that is
    shifted by the weather index (anticyclone → calmer winds).
    Using daily weather values gives stable mean calibration while the
    OU process captures realistic intra-day ramp variability.
    """
    p = SEASONS[season]
    mu = p["wind_mean"][country]
    sigma = p["wind_std"][country]

    WEATHER_SCALE = 0.12   # max ±0.12 CF shift per unit of daily weather

    # Daily target means, one per day
    daily_mu = np.clip(
        mu + p["wind_weather_corr"] * WEATHER_SCALE * daily_weather,
        0.05, 0.95,
    )

    # OU parameters: 6-hour mean-reversion timescale for intra-day noise.
    # sigma_step is calibrated to give the desired stationary std.
    theta = 1.0 / 6.0
    sigma_step = sigma * np.sqrt(2.0 * theta)

    cf = np.zeros(HOURS_PER_WEEK)
    cf[0] = np.clip(mu + sigma * rng.standard_normal(), 0.0, 1.0)
    for t in range(1, HOURS_PER_WEEK):
        cf[t] = (cf[t - 1]
                 + theta * (daily_mu[t // 24] - cf[t - 1])
                 + sigma_step * rng.standard_normal())

    return np.clip(cf, 0.0, 1.0)


def _load_profile(avg_load_mw: float,
                  load_scale: float,
                  rng: np.random.Generator) -> np.ndarray:
    """
    168-hour load profile (MW).

    Double-peaked diurnal shape (morning 08:00, evening 19:00)
    with weekday/weekend scaling and small random noise.
    """
    hours = np.arange(24)
    diurnal = (
        0.60
        + 0.28 * np.exp(-0.5 * ((hours - 8) / 1.8) ** 2)   # morning peak
        + 0.38 * np.exp(-0.5 * ((hours - 19) / 2.5) ** 2)  # evening peak
    )
    diurnal /= diurnal.mean()  # normalise so mean = 1.0

    profile = np.zeros(HOURS_PER_WEEK)
    for day in range(7):
        weekend = 0.85 if day >= 5 else 1.0
        for h in range(24):
            t = day * 24 + h
            noise = 1.0 + 0.02 * rng.standard_normal()
            profile[t] = diurnal[h] * weekend * noise

    return profile * avg_load_mw * load_scale


# ---------------------------------------------------------------------------
# Snapshot index and weights
# ---------------------------------------------------------------------------

def make_snapshots(seasons: list[str] | None = None) -> pd.DatetimeIndex:
    """
    Return a DatetimeIndex of N × 168 hourly timestamps.

    Parameters
    ----------
    seasons:
        Subset of season names to include, e.g. ["summer"] or ["spring", "summer"].
        Defaults to all four seasons.
    """
    active = seasons if seasons is not None else list(SEASONS)
    indices = [
        pd.date_range(SEASONS[s]["week_start"], periods=HOURS_PER_WEEK, freq="h")
        for s in active
    ]
    return indices[0].append(indices[1:])


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def attach_timeseries(n: pypsa.Network, seed: int = 42) -> None:
    """
    Generate synthetic time series and attach them to the network.

    Modifies *n* in-place:
    - Sets snapshot weightings (each hour = 13 weeks).
    - Sets p_max_pu for wind and solar generators.
    - Sets p_max_pu = 0.85 (constant) for nuclear generators.
    - Replaces constant Load.p_set with an hourly profile.

    Parameters
    ----------
    n:
        Network returned by build_network(), whose snapshots must already
        be the output of make_snapshots().
    seed:
        Random seed for reproducibility.
    """
    rng = np.random.default_rng(seed)

    # --- Snapshot weights ---
    n.snapshot_weightings["generators"] = float(SNAPSHOT_WEIGHT)
    n.snapshot_weightings["objective"] = float(SNAPSHOT_WEIGHT)
    n.snapshot_weightings["stores"] = 1.0  # physical hours between snapshots

    # Determine which seasons are active in this network's snapshots.
    # Always advance the RNG through all 4 seasons in order so that seed=42
    # produces the same per-season profiles regardless of the active subset.
    active_seasons = {
        s for s, p in SEASONS.items()
        if pd.Timestamp(p["week_start"]) in n.snapshots
    }

    wind_profiles: dict[str, list[np.ndarray]] = {}
    solar_profiles: dict[str, list[np.ndarray]] = {}
    load_profiles: dict[str, list[np.ndarray]] = {}

    for season in SEASONS:
        weather = _synoptic_weather(rng)

        wind_cfs  = {c: _wind_cf(season, c, weather, rng)  for c in LATITUDES}
        solar_cfs = {c: _solar_cf(season, c, weather, rng) for c in LATITUDES}
        load_arrs = {
            c: _load_profile(avg_mw, SEASONS[season]["load_scale"], rng)
            for c, avg_mw in AVERAGE_LOADS.items()
        }

        if season not in active_seasons:
            continue   # RNG already advanced; skip accumulating this season

        for c, cf in wind_cfs.items():
            wind_profiles.setdefault(c, []).append(cf)
        for c, cf in solar_cfs.items():
            solar_profiles.setdefault(c, []).append(cf)
        for c, arr in load_arrs.items():
            load_profiles.setdefault(c, []).append(arr)

    wind_annual  = {c: np.concatenate(v) for c, v in wind_profiles.items()}
    solar_annual = {c: np.concatenate(v) for c, v in solar_profiles.items()}
    load_annual  = {c: np.concatenate(v) for c, v in load_profiles.items()}

    idx = n.snapshots

    # --- Attach wind p_max_pu ---
    for gen in n.generators.index[n.generators.carrier == "wind"]:
        country = n.generators.at[gen, "bus"]   # bus name == country name
        n.generators_t.p_max_pu[gen] = pd.Series(
            wind_annual[country], index=idx
        )

    # --- Attach solar p_max_pu ---
    for gen in n.generators.index[n.generators.carrier == "solar"]:
        country = n.generators.at[gen, "bus"]
        n.generators_t.p_max_pu[gen] = pd.Series(
            solar_annual[country], index=idx
        )

    # --- Nuclear: constant 85% availability ---
    for gen in n.generators.index[n.generators.carrier == "nuclear"]:
        n.generators_t.p_max_pu[gen] = pd.Series(0.85, index=idx)

    # --- Attach load time series ---
    for load in n.loads.index:
        country = n.loads.at[load, "bus"]
        n.loads_t.p_set[load] = pd.Series(load_annual[country], index=idx)
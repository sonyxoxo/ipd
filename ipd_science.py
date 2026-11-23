"""Scientific experiments for daily household active-power profiles.

Do not modify the raw data. Measurements are per-minute averages in kW.
Scientific claims are exploratory: permutation exchangeability and bootstrap
block independence are modeling assumptions, not facts inferred from p-values.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SEED = 2026
MONTHS = ("2008-01", "2008-04", "2008-07", "2008-09")
MINUTES_DAY = 1440


def _save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, sep=";", encoding="utf-8-sig", float_format="%.10f")


def as_days(minutes: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """One row per day, exactly 1440 columns; incomplete boundary days retained."""
    selected = minutes[["timestamp", "Global_active_power"]].copy()
    if start is not None:
        selected = selected.loc[selected.timestamp.ge(pd.Timestamp(start))]
    if end is not None:
        selected = selected.loc[selected.timestamp.lt(pd.Timestamp(end))]
    selected["date"] = selected.timestamp.dt.normalize()
    selected["minute"] = selected.timestamp.dt.hour * 60 + selected.timestamp.dt.minute
    if selected.duplicated(["date", "minute"]).any():
        raise ValueError("Duplicate clock minutes; timezone/DST mapping must be resolved")
    days = selected.pivot(index="date", columns="minute", values="Global_active_power")
    return days.reindex(columns=range(MINUTES_DAY))


def complete_month_days(minutes: pd.DataFrame, month: str) -> tuple[pd.DataFrame, dict]:
    start = pd.Period(month).start_time
    end = (pd.Period(month) + 1).start_time
    days = as_days(minutes, str(start), str(end))
    expected = pd.Period(month).days_in_month
    complete = days.dropna(axis=0, how="any")
    info = {"month": month, "calendar_days": expected, "present_days": len(days),
            "complete_days": len(complete), "excluded_days": expected - len(complete)}
    return complete, info


def select_control(minutes: pd.DataFrame, preferred: str = "2008-09", minimum_days: int = 14) -> pd.DataFrame | None:
    """Prefer the complete September 2008 UCI month, else longest full-day run."""
    start = str(pd.Period(preferred).start_time)
    end = str((pd.Period(preferred) + 1).start_time)
    preferred_days = as_days(minutes, start, end)
    if len(preferred_days) == pd.Period(preferred).days_in_month and preferred_days.notna().all().all():
        return preferred_days
    days = as_days(minutes)
    valid = days.notna().all(axis=1).to_numpy()
    longest = (0, 0)
    begin = None
    for i, state in enumerate(np.r_[valid, False]):
        if state and begin is None:
            begin = i
        if not state and begin is not None:
            if i - begin > longest[1] - longest[0]:
                longest = (begin, i)
            begin = None
    if longest[1] - longest[0] < minimum_days:
        return None
    return days.iloc[longest[0]:min(longest[1], longest[0] + 30)]


def hourly_daily(days: np.ndarray) -> np.ndarray:
    arr = np.asarray(days, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != MINUTES_DAY:
        raise ValueError("Expected (n_days, 1440) array")
    return arr.reshape(-1, 24, 60).mean(axis=2)


def block_groups(values: np.ndarray, labels: np.ndarray, months: tuple[str, ...],
                 block_days: int, dates: np.ndarray | None = None) -> list[np.ndarray]:
    """Build nonoverlapping blocks within calendar-contiguous runs only.

    Complete-day deletion MUST NOT create fake adjacent days: when dates are
    provided, blocks never cross a gap in real calendar days.
    """
    groups: list[np.ndarray] = []
    for month in months:
        part = np.asarray(values[labels == month], dtype=float)
        month_dates = pd.DatetimeIndex(dates[labels == month]) if dates is not None else None
        if month_dates is None:
            segments = [part]
        else:
            if not month_dates.is_monotonic_increasing:
                raise ValueError("Dates must be sorted")
            discontinuities = np.flatnonzero(np.diff(month_dates.asi8) != 86400 * 10**9) + 1
            segments = np.split(part, discontinuities)
        pieces = []
        for segment in segments:
            n = len(segment) // block_days
            if n:
                x = segment[:n*block_days].reshape(n, block_days, -1).mean(axis=1)
                pieces.append(x[np.isfinite(x).all(axis=1)])
        if not pieces:
            return []
        valid = np.concatenate(pieces)
        if len(valid) < 2:
            return []
        groups.append(valid)
    return groups


def _between_statistic(groups: list[np.ndarray]) -> float:
    sizes = np.array([len(g) for g in groups])
    pooled_center = np.concatenate(groups).mean(axis=0)
    return float(sum(n * np.sum((g.mean(axis=0) - pooled_center) ** 2) for n, g in zip(sizes, groups)))


def permutation_p(groups: list[np.ndarray], rng: np.random.Generator, repetitions: int = 999) -> float:
    """Block-level unrestricted permutation; exploratory under exchangeability."""
    if repetitions < 1:
        raise ValueError("At least 1 permutation required")
    x = np.concatenate(groups)
    splits = np.cumsum([len(g) for g in groups])[:-1]
    observed = _between_statistic(groups)
    exceed = sum(_between_statistic(np.split(x[rng.permutation(len(x))], splits)) >= observed - 1e-12
                 for _ in range(repetitions))
    return (exceed + 1) / (repetitions + 1)


def holm(pvalues: list[float] | np.ndarray) -> np.ndarray:
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adjusted = np.maximum.accumulate(p[order] * np.arange(len(p), 0, -1))
    out = np.empty_like(adjusted)
    out[order] = np.minimum(adjusted, 1)
    return out


def analyze_h1(minutes: pd.DataFrame, out: Path, months: tuple[str, ...] = MONTHS,
               repetitions: int = 999, block_sizes: tuple[int, ...] = (3, 5, 7)) -> dict:
    days_list, labels_list, date_list, info = [], [], [], []
    for month in months:
        days, record = complete_month_days(minutes, month)
        info.append(record)
        if len(days):
            days_list.append(days.to_numpy(dtype=float))
            labels_list.extend([month] * len(days))
            date_list.extend(days.index.to_list())
    _save(pd.DataFrame(info), out / "06_h1_days.csv")
    if len(days_list) < 2:
        return {"status": "skipped", "reason": "fewer than 2 months have complete days"}
    labels = np.asarray(labels_list)
    dates = np.asarray(date_list, dtype="datetime64[ns]")
    hourly = hourly_daily(np.vstack(days_list))
    mean_kw = hourly.mean(axis=1)
    shape = np.divide(hourly, mean_kw[:, None], out=np.full_like(hourly, np.nan),
                      where=mean_kw[:, None] > 0)
    amplitude = (hourly.max(axis=1) - hourly.min(axis=1)).reshape(-1, 1)
    angles = 2 * np.pi * hourly.argmax(axis=1) / 24
    peak = np.column_stack((np.cos(angles), np.sin(angles)))
    vals = {"shape": shape, "amplitude": amplitude, "peak_hour_circular": peak}
    active_months = tuple(m for m in months if m in labels)
    output = []
    for length in block_sizes:
        local_names, local_p, local_n = [], [], []
        for feature, arr in vals.items():
            groups = block_groups(arr, labels, active_months, length, dates=dates)
            if not groups:
                continue
            rng = np.random.default_rng(SEED + length + {"shape": 1, "amplitude": 2, "peak_hour_circular": 3}[feature])
            local_names.append(feature)
            local_n.append([len(g) for g in groups])
            local_p.append(permutation_p(groups, rng, repetitions))
        if local_p:
            for feature, sizes, pval, adj in zip(local_names, local_n, local_p, holm(local_p)):
                output.append({"feature": feature, "block_days": length, "p_value": pval,
                               "p_holm": adj, "n_blocks_total": sum(sizes),
                               "blocks_by_month": json.dumps(dict(zip(active_months, sizes)), ensure_ascii=False),
                               "permutations": repetitions})
    _save(pd.DataFrame(output), out / "06_h1_tests.csv")
    effects = []
    if {"2008-01", "2008-07"}.issubset(active_months):
        contrast = ("2008-01", "2008-07")
    else:
        contrast = (active_months[0], active_months[-1])
    groups = block_groups(mean_kw[:, None], labels, active_months, 5, dates=dates)
    if groups:
        first = groups[active_months.index(contrast[0])].ravel()
        second = groups[active_months.index(contrast[1])].ravel()
        rng = np.random.default_rng(SEED + 100)
        bs = np.array([rng.choice(first, len(first), replace=True).mean() -
                       rng.choice(second, len(second), replace=True).mean() for _ in range(repetitions)])
        lo, hi = np.quantile(bs, [.025, .975])
        effects.append({"first": contrast[0], "second": contrast[1],
                        "difference_kw": first.mean() - second.mean(), "ci_low_kw": lo,
                        "ci_high_kw": hi, "n_blocks_first": len(first), "n_blocks_second": len(second),
                        "bootstrap_repetitions": repetitions, "warning_small_n": min(len(first), len(second)) < 10})
    _save(pd.DataFrame(effects), out / "06_h1_effect.csv")
    # Quartile bands describe observed between-day variability, NOT a 95% confidence interval.
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for month in active_months:
        month_shape = shape[labels == month]
        avg = month_shape.mean(axis=0)
        lower, upper = np.quantile(month_shape, [.25, .75], axis=0)
        line, = ax.plot(np.arange(24), avg, label=month)
        ax.fill_between(np.arange(24), lower, upper, color=line.get_color(), alpha=.12)
    ax.set(xlabel="Час суток", ylabel="Мощность / среднесуточная мощность",
           title="H1: форма среднего почасового профиля (полные сутки)")
    ax.grid(alpha=.25); ax.legend()
    fig.tight_layout(); fig.savefig(out / "06_h1_profiles.png", dpi=180); plt.close(fig)
    # Day-of-week is a potential confounder; save a descriptive split.
    day_of_week = []
    for month, days in zip([i["month"] for i in info if i["complete_days"] > 0], days_list):
        # The retained daily matrix may have excluded days: use the actual complete-day index.
        complete, _ = complete_month_days(minutes, month)
        for name, group in (("weekday", complete.index.dayofweek < 5),
                            ("weekend", complete.index.dayofweek >= 5)):
            selected = complete.loc[group]
            day_of_week.append({"month": month, "type": name, "days": len(selected),
                                "mean_kw": float(selected.to_numpy().mean()) if len(selected) else np.nan})
    _save(pd.DataFrame(day_of_week), out / "06_h1_weekday_weekend.csv")
    return {"status": "ok", "months": list(active_months), "tests": len(output),
            "interpretation": "Exploratory permutation p-values; exchangeability not established"}


def missing_mask(n_days: int, fraction: float, scenario: str, rng: np.random.Generator) -> np.ndarray:
    n = n_days * MINUTES_DAY
    if n_days < 1 or not 0 < fraction < 1:
        raise ValueError("Invalid day count or fraction")
    count = round(n * fraction)
    mask = np.zeros(n, dtype=bool)
    if scenario == "continuous":
        start = int(rng.integers(0, n - count + 1))
        mask[start:start+count] = True
    elif scenario == "clustered_days":
        eligible_days = max(1, int(np.ceil(n_days * 0.2)))
        eligible_days = max(eligible_days, int(np.ceil(count / MINUTES_DAY)))
        days = rng.choice(n_days, size=min(n_days, eligible_days), replace=False)
        candidates = np.concatenate([np.arange(day*MINUTES_DAY, (day+1)*MINUTES_DAY) for day in days])
        mask[rng.choice(candidates, size=count, replace=False)] = True
    elif scenario in ("random", "evening"):
        if scenario == "random":
            candidates = np.arange(n)
        else:
            candidates = np.flatnonzero(np.tile(np.arange(MINUTES_DAY) >= 18*60, n_days))
        if count > len(candidates):
            raise ValueError("Requested fraction exceeds eligible interval")
        mask[rng.choice(candidates, count, replace=False)] = True
    else:
        raise ValueError(f"Unknown scenario: {scenario}")
    assert mask.sum() == count
    return mask


def fixed_gap_mask(n_days: int, gap_length: int, fraction: float, rng: np.random.Generator) -> np.ndarray:
    """Non-overlapping runs of prescribed lengths, inside days, exact total count.

    Short remainder may be present if target count is not divisible by length.
    """
    if not 1 <= gap_length <= MINUTES_DAY // 2 or not 0 < fraction < .5:
        raise ValueError("Gap length 1..720, fraction in (0, 0.5)")
    total = n_days * MINUTES_DAY
    target = round(total * fraction)
    mask = np.zeros((n_days, MINUTES_DAY), dtype=bool)
    for _ in range(16):
        candidates = []
        for day in range(n_days):
            shift = int(rng.integers(0, gap_length)) if gap_length > 1 else 0
            candidates.extend((day, st) for st in range(shift, MINUTES_DAY - gap_length + 1, gap_length))
        rng.shuffle(candidates)
        n_blocks = target // gap_length
        if len(candidates) >= n_blocks:
            for day, st in candidates[:n_blocks]:
                mask[day, st:st + gap_length] = True
            rest = target - int(mask.sum())
            if rest:
                free = np.flatnonzero(~mask.ravel())
                mask.ravel()[rng.choice(free, rest, replace=False)] = True
            return mask.ravel()
    raise RuntimeError("Cannot construct mask")


def profile(values: np.ndarray) -> np.ndarray:
    a = np.asarray(values, dtype=float).reshape(-1, MINUTES_DAY)
    n = np.isfinite(a).sum(axis=0)
    return np.divide(np.nansum(a, axis=0), n, out=np.full(MINUTES_DAY, np.nan), where=n > 0)


def metrics(values: np.ndarray | None, baseline_profile: np.ndarray,
            common_support: np.ndarray | None = None, original: np.ndarray | None = None,
            artificial_mask: np.ndarray | None = None) -> dict:
    if values is None or np.asarray(values).size == 0:
        return {"mae_kw": np.nan, "rmse_kw": np.nan, "coverage_pct": np.nan,
                "common_mae_kw": np.nan, "energy_bias_pct": np.nan,
                "peak_change_pct": np.nan, "imputed_mae_kw": np.nan,
                "imputed_count": 0, "imputed_coverage_pct": np.nan}
    p = profile(values)
    available = np.isfinite(p) & np.isfinite(baseline_profile)
    if not available.any():
        return metrics(None, baseline_profile)
    diff = p[available] - baseline_profile[available]
    common = available if common_support is None else available & common_support
    full_energy = baseline_profile.sum() / 60
    est_energy = p.sum() / 60 if available.all() else np.nan
    imputed = np.nan
    imputed_count = 0
    imputed_coverage_pct = np.nan
    if original is not None and artificial_mask is not None:
        estimate = np.asarray(values, dtype=float).ravel()
        truth = np.asarray(original, dtype=float).ravel()
        where = artificial_mask & np.isfinite(estimate) & np.isfinite(truth)
        imputed_count = int(where.sum())
        if artificial_mask.sum():
            imputed_coverage_pct = 100 * imputed_count / int(artificial_mask.sum())
        if where.any():
            imputed = float(np.abs(estimate[where] - truth[where]).mean())
    return {"mae_kw": float(np.abs(diff).mean()), "rmse_kw": float(np.sqrt(np.mean(diff**2))),
            "coverage_pct": float(100*available.mean()),
            "common_mae_kw": float(np.abs(p[common] - baseline_profile[common]).mean()) if common.any() else np.nan,
            "energy_bias_pct": float(100*(est_energy / full_energy - 1)) if np.isfinite(est_energy) and full_energy > 0 else np.nan,
            "peak_change_pct": float(100*(np.nanmax(p) / np.nanmax(baseline_profile) - 1)) if np.nanmax(baseline_profile) > 0 else np.nan,
            "imputed_mae_kw": imputed, "imputed_count": imputed_count,
            "imputed_coverage_pct": imputed_coverage_pct}


def interpolate_bounded(values: np.ndarray, max_gap: int) -> np.ndarray:
    """Internal linear interpolation of gaps <= max_gap; never crosses midnight."""
    if max_gap < 1:
        raise ValueError("max_gap must be positive")
    original = np.asarray(values, dtype=float)
    shape = original.shape
    daily = original.reshape(-1, MINUTES_DAY)
    result = np.empty_like(daily)
    for i, day in enumerate(daily):
        filled = pd.Series(day).interpolate(method="linear", limit_area="inside").to_numpy()
        missing = ~np.isfinite(day)
        starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
        ends = np.flatnonzero(missing & ~np.r_[missing[1:], False]) + 1
        for st, end in zip(starts, ends):
            if end - st > max_gap or st == 0 or end == MINUTES_DAY:
                filled[st:end] = np.nan
        result[i] = filled
    return result.reshape(shape)


def _summarize_trials(trials: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if trials.empty:
        return pd.DataFrame()
    return trials.groupby(keys, as_index=False).agg(
        experiments=("mae_kw", "size"), valid=("mae_kw", "count"),
        mean_mae_kw=("mae_kw", "mean"), mean_common_mae_kw=("common_mae_kw", "mean"),
        mean_rmse_kw=("rmse_kw", "mean"), mean_coverage_pct=("coverage_pct", "mean"),
        mean_energy_bias_pct=("energy_bias_pct", "mean"),
        mean_imputed_mae_kw=("imputed_mae_kw", "mean"),
        mean_imputed_count=("imputed_count", "mean"),
        mean_imputed_coverage_pct=("imputed_coverage_pct", "mean"),
        p025_mae_kw=("mae_kw", lambda x: x.quantile(.025)),
        p975_mae_kw=("mae_kw", lambda x: x.quantile(.975)))


def analyze_h2(control: pd.DataFrame, out: Path, repetitions: int = 100) -> pd.DataFrame:
    original = control.to_numpy(dtype=float).ravel()
    reference = profile(original)
    rng = np.random.default_rng(SEED)
    rows = []
    for fraction in (.01, .05, .10, .20):
        for scenario in ("random", "continuous", "evening"):
            for rep in range(repetitions):
                mask = missing_mask(len(control), fraction, scenario, rng)
                damaged = original.copy(); damaged[mask] = np.nan
                rows.append({"fraction": fraction, "scenario": scenario, "repeat": rep+1,
                             "removed_count": int(mask.sum()), **metrics(damaged, reference)})
    trials = pd.DataFrame(rows)
    summary = _summarize_trials(trials, ["fraction", "scenario"])
    _save(trials, out / "06_h2_trials.csv"); _save(summary, out / "06_h2_summary.csv")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for scenario, group in summary.groupby("scenario"):
        ax.plot(100 * group.fraction, group.mean_mae_kw, marker="o", label=scenario)
    ax.set(xlabel="Доля удалённых минут, %", ylabel="MAE профиля, кВт",
           title="H2: влияние расположения пропусков")
    ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(out / "06_h2_missing.png", dpi=180); plt.close(fig)
    return summary


def _h3_one(original: np.ndarray, reference: np.ndarray, mask: np.ndarray,
            scenario: str, repeat: int, gap_len: int | None = None) -> list[dict]:
    damaged = original.copy(); damaged[mask] = np.nan
    d = damaged.reshape(-1, MINUTES_DAY)
    complete = d[np.isfinite(d).all(axis=1)]
    methods = {"available": damaged,
               "linear_15": interpolate_bounded(damaged, 15),
               "linear_60": interpolate_bounded(damaged, 60),
               "complete_days": complete.ravel() if len(complete) else None}
    common = np.isfinite(reference)
    for name in ("available", "linear_15", "linear_60"):
        common &= np.isfinite(profile(methods[name]))
    rows = []
    for method, result in methods.items():
        rows.append({"scenario": scenario, "repeat": repeat, "gap_length": gap_len,
                     "method": method, "removed_count": int(mask.sum()),
                     "complete_days_remaining": int(len(complete)),
                     **metrics(result, reference, common, original if method.startswith("linear_") else None,
                               mask if method.startswith("linear_") else None)})
    return rows


def analyze_h3(control: pd.DataFrame, out: Path, repetitions: int = 30,
               gap_lengths: tuple[int, ...] = (1, 5, 15, 30, 60, 120),
               gap_repetitions: int = 15) -> pd.DataFrame:
    original = control.to_numpy(dtype=float).ravel()
    reference = profile(original)
    rng = np.random.default_rng(SEED + 1)
    rows = []
    for scenario in ("random", "continuous", "evening", "clustered_days"):
        for rep in range(repetitions):
            mask = missing_mask(len(control), .10, scenario, rng)
            rows.extend(_h3_one(original, reference, mask, scenario, rep+1))
    trials = pd.DataFrame(rows)
    summary = _summarize_trials(trials, ["scenario", "method"])
    _save(trials, out / "06_h3_trials.csv"); _save(summary, out / "06_h3_summary.csv")
    rng_gaps = np.random.default_rng(SEED + 2)
    gap_rows = []
    for gap in gap_lengths:
        for rep in range(gap_repetitions):
            mask = fixed_gap_mask(len(control), gap, .10, rng_gaps)
            gap_rows.extend(_h3_one(original, reference, mask, "fixed_gap", rep+1, gap))
    gap_trials = pd.DataFrame(gap_rows)
    gap_summary = _summarize_trials(gap_trials, ["gap_length", "method"])
    _save(gap_trials, out / "06_h3_gap_trials.csv")
    _save(gap_summary, out / "06_h3_gap_summary.csv")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for method in ("available", "linear_15", "linear_60"):
        group = gap_summary.loc[gap_summary.method.eq(method)]
        ax.plot(group.gap_length, group.mean_mae_kw, marker="o", label=method)
    ax.axvline(15, color="gray", linestyle=":", alpha=.5)
    ax.axvline(60, color="gray", linestyle=":", alpha=.5)
    ax.set(xlabel="Характерная длина искусственного пропуска, мин",
           ylabel="MAE среднего суточного профиля, кВт", title="H3: проверка порогов интерполяции")
    ax.grid(alpha=.25); ax.legend(); fig.tight_layout()
    fig.savefig(out / "06_h3_gaps.png", dpi=180); plt.close(fig)
    return summary


def physics_consistency(minutes: pd.DataFrame, out: Path) -> pd.DataFrame:
    """Compare total minute Wh to sum of three submeter Wh readings.

    Negative residuals are flagged, not clamped or discarded.
    """
    names = [f"Sub_metering_{i}" for i in (1,2,3)]
    if any(n not in minutes for n in names):
        return pd.DataFrame([{"status": "unavailable", "reason": "submeters absent"}])
    energy_wh = minutes["Global_active_power"] * (1000/60)
    sub_sum = minutes[names].sum(axis=1, min_count=3)
    residual = energy_wh - sub_sum
    valid = energy_wh.notna() & sub_sum.notna()
    result = pd.DataFrame([{"status": "ok", "valid_minutes": int(valid.sum()),
                            "negative_residual_minutes": int((residual[valid] < 0).sum()),
                            "negative_residual_pct": float(100*(residual[valid] < 0).mean()) if valid.any() else np.nan,
                            "median_residual_wh": float(residual[valid].median()) if valid.any() else np.nan,
                            "mean_residual_wh": float(residual[valid].mean()) if valid.any() else np.nan,
                            "interpretation": "Negative residual can reflect metering/rounding issues; do not force to zero"}])
    _save(result, out / "03_physics_consistency.csv")
    return result


def daily_autocorrelation(minutes: pd.DataFrame, out: Path) -> pd.DataFrame:
    """Exploratory daily lag-1 and lag-7 correlation on complete daily means."""
    days = as_days(minutes).dropna(how="any")
    if len(days) < 20:
        return pd.DataFrame([{"status": "skipped", "reason": "fewer than 20 complete days"}])
    means = days.mean(axis=1)
    pairs = []
    for lag in (1,7):
        aligned = pd.DataFrame({"left": means, "right": means.shift(lag, freq="D")}).dropna()
        pairs.append({"lag_days": lag, "pairs": len(aligned),
                      "correlation": float(aligned.left.corr(aligned.right)) if len(aligned) > 3 else np.nan})
    result = pd.DataFrame(pairs)
    _save(result, out / "06_daily_dependence.csv")
    return result




def source_quality_report(raw_measurements: pd.DataFrame, out: Path) -> pd.DataFrame:
    """Audit validity reasons saved while reading raw values, not synthetic zeros."""
    counts = raw_measurements.attrs.get("quality_counts", {})
    rows = []
    for name, values in counts.items():
        rows.append({"variable": name, **values})
    if not rows:
        for name in raw_measurements.attrs.get("measurement_columns", []):
            valid_column = f"valid_{name}"
            if valid_column in raw_measurements:
                rows.append({"variable": name, "valid": int(raw_measurements[valid_column].sum()),
                             "raw_missing": np.nan, "non_numeric": np.nan,
                             "not_physical_or_nonfinite": np.nan})
    result = pd.DataFrame(rows)
    if not result.empty:
        _save(result, out / "01_quality_reasons.csv")
    return result


def plot_missing_heatmap(hourly: pd.DataFrame, out: Path) -> None:
    """Calendar-month × hour heatmap showing where missingness concentrates."""
    if hourly.empty:
        return
    wide = hourly.pivot(index="month", columns="hour", values="missing_pct").reindex(columns=range(24))
    fig, ax = plt.subplots(figsize=(11, max(5, 0.23 * len(wide) + 2)))
    heat = ax.imshow(wide.to_numpy(), aspect="auto", interpolation="nearest", cmap="magma")
    ax.set_yticks(range(len(wide)), wide.index, fontsize=7)
    ax.set_xticks(range(0,24,2), range(0,24,2))
    ax.set(xlabel="Час суток", ylabel="Календарный месяц", title="Естественные пропуски по месяцам и часам, %")
    cb = fig.colorbar(heat, ax=ax, fraction=.03, pad=.02)
    cb.set_label("Отсутствующие минуты, %")
    fig.tight_layout(); fig.savefig(out / "06_natural_missing_heatmap.png", dpi=160); plt.close(fig)

def spectrum_of_daily_profile(minutes: pd.DataFrame, out: Path, preferred: str = "2008-09") -> pd.DataFrame:
    """Fourier harmonics of mean 24h shape (not year-to-year seasonality).

    The 1440-sample profile is treated as one periodic day. Frequencies in
    cycles/day; amplitude in kW. This is descriptive, not a significance test.
    """
    days, _ = complete_month_days(minutes, preferred)
    if len(days) < 7:
        return pd.DataFrame([{"status": "skipped", "reason": "fewer than 7 complete days"}])
    daily_profile = days.mean(axis=0).to_numpy(dtype=float)
    detrended = daily_profile - daily_profile.mean()
    f = np.fft.rfftfreq(MINUTES_DAY, d=1/MINUTES_DAY)
    amplitude = 2 * np.abs(np.fft.rfft(detrended))/MINUTES_DAY
    result = pd.DataFrame({"cycles_per_day": f, "amplitude_kw": amplitude})
    _save(result, out / "06_fft_mean_day.csv")
    fig, ax = plt.subplots(figsize=(9,4))
    subset = result.loc[(result.cycles_per_day >= 1) & (result.cycles_per_day <= 12)]
    ax.bar(subset.cycles_per_day, subset.amplitude_kw, width=.7)
    ax.set(xlabel="Гармоника, циклов в сутки", ylabel="Амплитуда, кВт",
           title=f"Спектр среднего суточного профиля {preferred} (описательно)")
    ax.set_xticks(np.arange(1,13)); ax.grid(axis="y", alpha=.2)
    fig.tight_layout(); fig.savefig(out / "06_fft_mean_day.png",dpi=180); plt.close(fig)
    return result


def natural_missing_hours(minutes: pd.DataFrame, out: Path) -> pd.DataFrame:
    table = minutes[["timestamp", "Global_active_power"]].copy()
    table["month"] = table.timestamp.dt.strftime("%Y-%m")
    table["hour"] = table.timestamp.dt.hour
    result = table.groupby(["month","hour"],as_index=False).agg(
        expected=("timestamp","size"), observed=("Global_active_power","count"))
    result["missing_pct"] = 100 * (result.expected - result.observed)/result.expected
    _save(result, out / "06_natural_missing_by_hour.csv")
    return result

def run_science(minutes: pd.DataFrame, output_dir: Path, *, h2_repetitions: int = 100,
                h3_repetitions: int = 30, gap_repetitions: int = 15,
                h1_permutations: int = 999) -> dict:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {"h1": analyze_h1(minutes, out, repetitions=h1_permutations)}
    physics_consistency(minutes, out)
    daily_autocorrelation(minutes, out)
    plot_missing_heatmap(natural_missing_hours(minutes, out), out)
    spectrum_of_daily_profile(minutes, out)
    control = select_control(minutes)
    if control is None:
        report["h2"] = report["h3"] = "skipped: no 14+ consecutive complete days"
    else:
        report["control_start"] = str(control.index.min().date())
        report["control_end"] = str(control.index.max().date())
        analyze_h2(control, out, h2_repetitions)
        analyze_h3(control, out, h3_repetitions, gap_repetitions=gap_repetitions)
        report["h2"] = report["h3"] = "ok"
    report["scientific_limitations"] = [
        "one household", "comparison periods not proof of seasonality",
        "permutation exchangeability not verified", "few independent bootstrap blocks",
        "missing-at-random simulation not validation of real missingness",
        "MAE on variable support must be accompanied by coverage and common-support MAE"]
    (out / "06_scientific_status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


def write_manifest(directory: Path) -> Path:
    """SHA-256 manifest of all generated files for auditable exports."""
    directory = Path(directory)
    items = {}
    for item in sorted(directory.rglob("*")):
        if item.is_file() and item.name != "manifest_sha256.json":
            items[item.relative_to(directory).as_posix()] = hashlib.sha256(item.read_bytes()).hexdigest()
    p = directory / "manifest_sha256.json"
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return p

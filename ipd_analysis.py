"""Общие расчёты для поминутных измерений электропотребления.

Все пути определяются относительно этого файла, а не текущего сеанса Colab.
Исходные файлы никогда не перезаписываются.
"""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import re
import zipfile

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parent
RAW_DIR = REPO_ROOT / "data" / "raw"
RESULTS_DIR = REPO_ROOT / "результаты"
MEASUREMENTS = (
    "Global_active_power", "Global_reactive_power", "Voltage",
    "Global_intensity", "Sub_metering_1", "Sub_metering_2", "Sub_metering_3",
)
SEASONAL_EXAMPLE = ("2008-01", "2008-04", "2008-07", "2008-09")
MISSING_EXAMPLE = ("2009-08", "2010-08")
VALID_EXTENSIONS = {".txt", ".csv", ".tsv", ".zip"}


def input_files(raw_dir: Path = RAW_DIR) -> list[Path]:
    """Находит все исходные файлы в data/raw, в том числе внутри подпапок."""
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"Каталог исходных данных отсутствует: {raw_dir}")
    files = sorted(
        path for path in raw_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS
    )
    if not files:
        raise FileNotFoundError(
            f"В {raw_dir} нет TXT/CSV/TSV/ZIP. Добавьте файл в репозиторий "
            "и выполните git pull; ручная загрузка в Colab не требуется."
        )
    return files


def choose_source(source: str | Path | None = None) -> Path:
    """Выбирает файл явно; при нескольких файлах требует осознанного выбора."""
    if source is not None:
        path = Path(source).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            raise FileNotFoundError(f"Не найден исходный файл в репозитории: {path}")
        return path.resolve()
    files = input_files()
    if len(files) > 1:
        relative_names = "\n".join(str(p.relative_to(REPO_ROOT)) for p in files)
        raise ValueError(
            "В репозитории несколько файлов. Укажите source явно либо запустите "
            f"пакетный анализ. Файлы:\n{relative_names}"
        )
    return files[0]


@contextmanager
def _source_stream(path: Path):
    """Открывает файл или единственный поддерживаемый файл внутри ZIP."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [
                name for name in archive.namelist()
                if not name.endswith("/")
                and Path(name).suffix.lower() in {".txt", ".csv", ".tsv"}
            ]
            if len(members) != 1:
                raise ValueError(
                    f"ZIP {path.name}: найдено {len(members)} таблиц; "
                    "ожидается ровно одна. Разделите архив или явно выберите файл."
                )
            with archive.open(members[0]) as stream:
                yield stream
    else:
        with path.open("rb") as stream:
            yield stream


def load_measurements(source: str | Path | None = None) -> pd.DataFrame:
    """Один раз читает файл, проверяет схему и создаёт числовую рабочую таблицу.

    Допустимы исходные столбцы Date + Time или один столбец datetime/timestamp.
    Для неизвестного формата выводится понятная ошибка, без угадывания физики.
    """
    path = choose_source(source)
    with _source_stream(path) as stream:
        header = stream.readline().decode("utf-8-sig").strip()
    delimiter = max((";", "\t", ","), key=header.count)
    if header.count(delimiter) == 0:
        raise ValueError(f"Не удалось распознать разделитель столбцов в {path.name}")
    with _source_stream(path) as stream:
        raw = pd.read_csv(
            stream, sep=delimiter, encoding="utf-8-sig", low_memory=False,
            na_values=["?", "", "NA", "N/A", "NULL", "null"],
        )
    raw.columns = raw.columns.str.strip()
    if "Date" in raw and "Time" in raw:
        timestamps = pd.to_datetime(
            raw["Date"].astype("string") + " " + raw["Time"].astype("string"),
            format="%d/%m/%Y %H:%M:%S", errors="coerce",
        )
    elif "timestamp" in raw or "datetime" in raw:
        time_column = "timestamp" if "timestamp" in raw else "datetime"
        timestamps = pd.to_datetime(raw[time_column], errors="coerce")
    else:
        raise ValueError(
            f"{path.name}: нужны Date и Time либо timestamp/datetime. "
            f"Фактические столбцы: {list(raw.columns)}"
        )
    if timestamps.isna().any():
        raise ValueError(
            f"{path.name}: не удалось распознать {int(timestamps.isna().sum())} "
            "временных меток. Проверьте формат дат."
        )
    present = [name for name in MEASUREMENTS if name in raw]
    if "Global_active_power" not in present:
        raise ValueError(
            f"{path.name}: нет Global_active_power (активная мощность в кВт). "
            "Для другой схемы требуется явное сопоставление столбцов и единиц."
        )
    data = pd.DataFrame({"timestamp": timestamps})
    unknown_values = {}
    for name in present:
        number = pd.to_numeric(raw[name], errors="coerce")
        unknown_values[name] = int((raw[name].notna() & number.isna()).sum())
        finite = pd.Series(np.isfinite(number.to_numpy(dtype=float)), index=raw.index)
        valid = finite & number.notna()
        if name == "Voltage":
            valid &= number > 0
        elif name != "Global_reactive_power":
            valid &= number >= 0
        data[name] = number.where(valid)
        data[f"valid_{name}"] = valid
    data = data.sort_values("timestamp", kind="stable").reset_index(drop=True)
    data.attrs.update({
        "source": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path),
        "unknown_values": unknown_values,
        "original_rows": len(raw),
        "measurement_columns": present,
    })
    return data


def audit(data: pd.DataFrame) -> pd.DataFrame:
    """Краткая проверка меток, пропусков, повторений и исходной схемы."""
    timestamps = data["timestamp"]
    differences = timestamps.diff()
    return pd.DataFrame([{
        "source": data.attrs.get("source", "unknown"),
        "rows": len(data),
        "start": timestamps.min(),
        "end": timestamps.max(),
        "duplicate_timestamps": int(timestamps.duplicated().sum()),
        "non_minute_transitions": int((differences.dropna() != pd.Timedelta(minutes=1)).sum()),
        "unknown_active_power": int(data["Global_active_power"].isna().sum()),
        "non_numeric_active_power": data.attrs.get("unknown_values", {}).get("Global_active_power", 0),
    }])


def regular_minutes(data: pd.DataFrame, max_minutes: int = 10_000_000) -> pd.DataFrame:
    """Создаёт минутную сетку; отсутствующие строки становятся явными NaN.

    Никакой интерполяции нет. Повторы времени запрещаются, чтобы не
    скрывать ошибки и не завышать статистику.
    """
    if data.empty:
        raise ValueError("Исходный файл не содержит измерений")
    if data["timestamp"].duplicated().any():
        raise ValueError(
            "Временные метки повторяются. Проверьте аудит и устраните "
            "причину дубликатов до статистической обработки."
        )
    if data["timestamp"].dt.second.ne(0).any():
        raise ValueError("Ожидаются поминутные метки с секундами 00")
    if len(data) >= 10:
        steps = data["timestamp"].diff().dropna()
        one_minute_fraction = (steps == pd.Timedelta(minutes=1)).mean()
        if one_minute_fraction < 0.05 and steps.median() > pd.Timedelta(minutes=1):
            raise ValueError(
                "Измерения, вероятно, записаны не каждую минуту. "
                "Эта методика рассчитана на поминутные данные; проверьте шаг записи."
            )
    span = int((data["timestamp"].max() - data["timestamp"].min()) / pd.Timedelta(minutes=1)) + 1
    if span > max_minutes:
        raise ValueError(f"Слишком большой временной диапазон: {span} минут")
    grid = pd.date_range(data["timestamp"].min(), data["timestamp"].max(), freq="min")
    indexed = data.set_index("timestamp").reindex(grid)
    indexed.index.name = "timestamp"
    for name in indexed.columns:
        if name.startswith("valid_"):
            indexed[name] = indexed[name].eq(True)
    return indexed.reset_index()


def monthly_coverage(minutes: pd.DataFrame) -> pd.DataFrame:
    """Раздельно считает полноту периода записи и полного календарного месяца."""
    grouped = minutes.groupby(minutes["timestamp"].dt.to_period("M"), sort=True)
    result = grouped.agg(
        expected_in_record=("timestamp", "size"),
        valid_power=("valid_Global_active_power", "sum"),
    ).reset_index(names="month")
    result["month"] = result["month"].astype(str)
    result["expected_calendar"] = result["month"].map(
        lambda month: pd.Period(month).days_in_month * 1440
    )
    result["missing_or_invalid"] = result["expected_in_record"] - result["valid_power"]
    result["coverage_record_pct"] = 100 * result["valid_power"] / result["expected_in_record"]
    result["coverage_calendar_pct"] = 100 * result["valid_power"] / result["expected_calendar"]
    return result

def missing_runs(minutes: pd.DataFrame) -> pd.DataFrame:
    """Ищет непрерывные пропуски, включая строки с отсутствующим временем."""
    missing = ~minutes["valid_Global_active_power"]
    run_id = missing.ne(missing.shift(fill_value=False)).cumsum()
    gaps = minutes.loc[missing, ["timestamp"]].copy()
    gaps["run_id"] = run_id.loc[missing].to_numpy()
    if gaps.empty:
        return pd.DataFrame(columns=["start", "end", "minutes", "crosses_month"])
    runs = gaps.groupby("run_id")["timestamp"].agg(
        start="min", end="max", minutes="size"
    ).reset_index(drop=True)
    runs["crosses_month"] = runs["start"].dt.to_period("M") != runs["end"].dt.to_period("M")
    return runs.sort_values("minutes", ascending=False).reset_index(drop=True)


def convert_energy(minutes: pd.DataFrame) -> pd.DataFrame:
    """E=P×(1/60 часа); подсчётчики Вт·ч переводятся в кВт·ч."""
    result = minutes.copy()
    result["active_energy_kwh"] = result["Global_active_power"] / 60.0
    for number in range(1, 4):
        column = f"Sub_metering_{number}"
        if column in result:
            result[f"sub_{number}_energy_kwh"] = result[column] / 1000.0
    known = result["Global_active_power"].notna()
    if not np.allclose(
        result.loc[known, "active_energy_kwh"] * 60,
        result.loc[known, "Global_active_power"],
    ):
        raise AssertionError("Не прошла проверка единиц энергии")
    return result


def monthly_statistics(minutes: pd.DataFrame) -> pd.DataFrame:
    """Описательная статистика доступных минут, без заполнения пропусков."""
    series = minutes["Global_active_power"]
    grouped = series.groupby(minutes["timestamp"].dt.to_period("M"))
    values = grouped.agg(
        observations="count", mean_kw="mean", median_kw="median",
        min_kw="min", max_kw="max", std_kw=lambda x: x.std(ddof=0),
        q1_kw=lambda x: x.quantile(0.25), q3_kw=lambda x: x.quantile(0.75),
    ).reset_index(names="month")
    values["month"] = values["month"].astype(str)
    values["iqr_kw"] = values["q3_kw"] - values["q1_kw"]
    values = values.merge(monthly_coverage(minutes)[["month", "coverage_record_pct", "coverage_calendar_pct"]], on="month")
    return values


def select_months(minutes: pd.DataFrame, preferred: tuple[str, ...] = SEASONAL_EXAMPLE, limit: int = 4) -> list[str]:
    """Берёт исследовательские месяцы, если они существуют; иначе первые доступные."""
    available = sorted(minutes["timestamp"].dt.strftime("%Y-%m").unique().tolist())
    selected = [month for month in preferred if month in available]
    return selected if len(selected) == len(preferred) else available[:limit]


def daily_profiles(minutes: pd.DataFrame, months: list[str] | None = None) -> pd.DataFrame:
    """Профиль 1440 минут каждого месяца: среднее, медиана, квартили, полнота."""
    months = months or select_months(minutes)
    selected = minutes.loc[minutes["timestamp"].dt.strftime("%Y-%m").isin(months)].copy()
    if selected.empty:
        raise ValueError(f"В данных нет выбранных месяцев: {months}")
    selected["month"] = selected["timestamp"].dt.strftime("%Y-%m")
    selected["minute_of_day"] = selected["timestamp"].dt.hour * 60 + selected["timestamp"].dt.minute
    grouped = selected.groupby(["month", "minute_of_day"])["Global_active_power"]
    profile = grouped.agg(
        mean_kw="mean", median_kw="median", q1_kw=lambda x: x.quantile(0.25),
        q3_kw=lambda x: x.quantile(0.75), n_observed="count", n_expected="size",
    )
    full_index = pd.MultiIndex.from_product([months, range(1440)], names=["month", "minute_of_day"])
    profile = profile.reindex(full_index).reset_index()
    profile[["n_observed", "n_expected"]] = profile[["n_observed", "n_expected"]].fillna(0).astype(int)
    profile["coverage_pct"] = (100 * profile["n_observed"] / profile["n_expected"].replace(0, np.nan))
    profile["iqr_kw"] = profile["q3_kw"] - profile["q1_kw"]
    return profile


def hourly_profiles(minutes: pd.DataFrame, months: list[str] | None = None) -> pd.DataFrame:
    """Почасовое среднее с весом по ВСЕМ доступным минутам, а не среднее из средних."""
    months = months or select_months(minutes)
    selected = minutes.loc[minutes["timestamp"].dt.strftime("%Y-%m").isin(months)].copy()
    selected["month"] = selected["timestamp"].dt.strftime("%Y-%m")
    selected["hour"] = selected["timestamp"].dt.hour
    return selected.groupby(["month", "hour"], as_index=False).agg(
        mean_kw=("Global_active_power", "mean"),
        n_observed=("Global_active_power", "count"),
        n_expected=("timestamp", "size"),
    )


def smooth_profiles(profiles: pd.DataFrame, windows: tuple[int, ...] = (15, 61)) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Циклическое сглаживание профиля с проверкой достаточности точек."""
    if any(window < 3 or window % 2 == 0 or window > 1439 for window in windows):
        raise ValueError("Окно сглаживания должно быть нечётным, от 3 до 1439 минут")
    smoothed = profiles.copy()
    comparisons = []
    for month, group in smoothed.groupby("month", sort=False):
        part = group.sort_values("minute_of_day")
        baseline = part["mean_kw"].to_numpy(dtype=float)
        if len(baseline) != 1440 or not np.isfinite(baseline).any():
            continue
        for window in windows:
            half = window // 2
            circular = np.r_[baseline[-half:], baseline, baseline[:half]]
            rolling = pd.Series(circular).rolling(
                window, center=True, min_periods=max(1, int(np.ceil(window * 0.8)))
            ).mean().iloc[half:half + 1440].to_numpy()
            smoothed.loc[part.index, f"smooth_{window}_kw"] = rolling
            valid = np.isfinite(baseline) & np.isfinite(rolling)
            differences = baseline[valid] - rolling[valid]
            peak_original = np.nanmax(baseline)
            peak_smoothed = np.nanmax(rolling) if np.isfinite(rolling).any() else np.nan
            comparisons.append({
                "month": month, "window_minutes": window,
                "original_peak_kw": peak_original, "smoothed_peak_kw": peak_smoothed,
                "peak_reduction_pct": (
                    100 * (peak_original - peak_smoothed) / peak_original
                    if peak_original > 0 else np.nan
                ),
                "mae_kw": float(np.mean(np.abs(differences))) if len(differences) else np.nan,
                "rmse_kw": float(np.sqrt(np.mean(differences**2))) if len(differences) else np.nan,
            })
    return smoothed, pd.DataFrame(comparisons)


def compare_complete_days(minutes: pd.DataFrame, months: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Сравнивает все измерения и полные сутки; не подменяет отсутствие полных суток нулём."""
    profiles = []
    summary = []
    period_index = minutes["timestamp"].dt.to_period("M")
    for month in months:
        part = minutes.loc[period_index.eq(pd.Period(month))].copy()
        if part.empty:
            continue
        part["date"] = part["timestamp"].dt.normalize()
        part["minute_of_day"] = part["timestamp"].dt.hour * 60 + part["timestamp"].dt.minute
        day_counts = part.groupby("date")["Global_active_power"].agg(["count", "size"])
        complete_dates = day_counts.index[(day_counts["count"] == 1440) & (day_counts["size"] == 1440)]
        complete_part = part.loc[part["date"].isin(complete_dates)]
        all_profile = part.groupby("minute_of_day")["Global_active_power"].mean().reindex(range(1440))
        complete_profile = complete_part.groupby("minute_of_day")["Global_active_power"].mean().reindex(range(1440))
        difference = (all_profile - complete_profile).dropna()
        profiles.append(pd.DataFrame({
            "month": month, "minute_of_day": range(1440),
            "all_observations_kw": all_profile.to_numpy(),
            "complete_days_kw": complete_profile.to_numpy(),
        }))
        summary.append({
            "month": month, "complete_days": len(complete_dates),
            "days_in_record": len(day_counts),
            "mean_all_kw": part["Global_active_power"].mean(),
            "mean_complete_kw": complete_part["Global_active_power"].mean(),
            "mae_kw": difference.abs().mean() if len(difference) else np.nan,
        })
    return pd.concat(profiles, ignore_index=True) if profiles else pd.DataFrame(), pd.DataFrame(summary)


def missing_experiment(minutes: pd.DataFrame, preferred_month: str = "2008-09", fraction: float = 0.1, seed: int = 2026):
    """Сравнивает случайные и непрерывные пропуски одинакового размера.

    Если полного календарного месяца без пропусков нет, опыт не проводится.
    """
    if not 0 < fraction < 1:
        raise ValueError("Доля искусственных пропусков должна быть между 0 и 1")
    coverage = monthly_coverage(minutes)
    eligible = coverage.loc[
        (coverage["coverage_calendar_pct"] == 100) &
        (coverage["expected_in_record"] == coverage["expected_calendar"]), "month"
    ].tolist()
    if not eligible:
        return pd.DataFrame(), pd.DataFrame()
    month = preferred_month if preferred_month in eligible else eligible[0]
    original = minutes.loc[minutes["timestamp"].dt.strftime("%Y-%m").eq(month)].copy().reset_index(drop=True)
    gap_count = int(round(len(original) * fraction))
    if gap_count < 1:
        return pd.DataFrame(), pd.DataFrame()
    rng = np.random.default_rng(seed)
    scenarios = {"original": original}
    random_missing = original.copy()
    random_missing.loc[rng.choice(len(original), gap_count, replace=False), "Global_active_power"] = np.nan
    scenarios["random"] = random_missing
    block_missing = original.copy()
    block_start = (len(original) - gap_count) // 2
    block_missing.loc[block_start:block_start + gap_count - 1, "Global_active_power"] = np.nan
    scenarios["continuous"] = block_missing
    profiles = []
    for scenario_name, scenario in scenarios.items():
        minute_index = scenario["timestamp"].dt.hour * 60 + scenario["timestamp"].dt.minute
        means = scenario.groupby(minute_index)["Global_active_power"].mean().reindex(range(1440))
        profiles.append(pd.DataFrame({
            "scenario": scenario_name, "month": month,
            "minute_of_day": range(1440), "mean_kw": means.to_numpy(),
        }))
    combined = pd.concat(profiles, ignore_index=True)
    pivot = combined.pivot(index="minute_of_day", columns="scenario", values="mean_kw")
    metrics = []
    for scenario_name, scenario in scenarios.items():
        differences = (pivot[scenario_name] - pivot["original"]).dropna()
        metrics.append({
            "month": month, "scenario": scenario_name,
            "missing_count": int(scenario["Global_active_power"].isna().sum()),
            "mean_kw": scenario["Global_active_power"].mean(),
            "mae_kw": differences.abs().mean() if len(differences) else np.nan,
        })
    return combined, pd.DataFrame(metrics)


def result_folder(source: Path) -> Path:
    """Уникальная папка результатов для конкретного файла из репозитория."""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", source.stem).strip("-") or "dataset"
    try:
        identity = source.resolve().relative_to(REPO_ROOT)
    except ValueError:
        identity = source.resolve()
    suffix = sha256(str(identity).encode("utf-8")).hexdigest()[:8]
    return RESULTS_DIR / f"{safe}-{suffix}"


def save_csv(frame: pd.DataFrame, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, sep=";", index=False, encoding="utf-8-sig", float_format="%.8f")
    return output


def export_labplot(profiles: pd.DataFrame) -> pd.DataFrame:
    """Одна таблица с английскими именами столбцов для импорта в LabPlot."""
    result = pd.DataFrame({"Hour": np.arange(1440) / 60})
    for month in profiles["month"].unique():
        part = profiles.loc[profiles["month"].eq(month)].sort_values("minute_of_day")
        result[f"P_{month}_kW"] = part["mean_kw"].to_numpy()
        result[f"Coverage_{month}_pct"] = part["coverage_pct"].to_numpy()
    return result

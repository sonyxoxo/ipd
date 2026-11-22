"""Пакетная обработка всех исходных таблиц из data/raw.

Пример: python run_analysis.py --all
        python run_analysis.py --file data/raw/measurements.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

from ipd_analysis import (
    REPO_ROOT, audit, choose_source, compare_complete_days, convert_energy,
    daily_profiles, export_labplot, hourly_profiles, input_files, load_measurements,
<<<<<<< HEAD
    missing_experiment, missing_runs, monthly_coverage, monthly_statistics,
    regular_minutes, result_folder, save_csv, select_months, smooth_profiles,
=======
    missing_experiment, missing_experiment_robustness, missing_runs, monthly_coverage,
    monthly_statistics, regular_minutes, result_folder, save_csv,
    save_run_metadata, select_months, smooth_profiles,
>>>>>>> 2d58bc45e57904272e3a30d5b66a02aefca628c0
)


def plot_profiles(profiles, output: Path) -> None:
    """Сравнение суточных профилей; пропуски остаются разрывами линии."""
    fig, (power_axis, coverage_axis) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
    )
    for month, group in profiles.groupby("month", sort=True):
        time_hours = group["minute_of_day"] / 60
        power_axis.plot(time_hours, group["mean_kw"], label=month, linewidth=1.3)
        coverage_axis.plot(time_hours, group["coverage_pct"], label=month, linewidth=1)
    power_axis.set(ylabel="Средняя активная мощность, кВт", title="Суточные профили")
    coverage_axis.set(xlabel="Время суток, ч", ylabel="Полнота, %", ylim=(0, 105), xlim=(0, 24))
    for axis in (power_axis, coverage_axis):
        axis.grid(alpha=0.25)
    power_axis.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_smoothing(smoothed, output: Path) -> None:
    months = smoothed["month"].unique()
    rows = int(np.ceil(len(months) / 2))
    fig, axes = plt.subplots(rows, 2, figsize=(13, 4 * rows), squeeze=False)
    for axis, month in zip(axes.flat, months):
        group = smoothed[smoothed["month"].eq(month)]
        time_hours = group["minute_of_day"] / 60
        axis.plot(time_hours, group["mean_kw"], label="Без сглаживания", linewidth=0.8)
        for column in group.columns:
            if column.startswith("smooth_"):
                axis.plot(time_hours, group[column], label=column, linewidth=1.2)
        axis.set(title=month, xlabel="Время суток, ч", ylabel="Мощность, кВт")
        axis.grid(alpha=0.25)
        axis.legend()
    for axis in axes.flat[len(months):]:
        axis.set_visible(False)
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_one_day(minutes, output: Path) -> None:
    """Исходные минутные значения одного дня без искусственного заполнения."""
    preferred = minutes.loc[minutes["timestamp"].dt.strftime("%Y-%m").eq("2008-09")]
    candidate = preferred if not preferred.empty else minutes
    daily = candidate.groupby(candidate["timestamp"].dt.normalize())["Global_active_power"].agg(["count", "size"])
    fully_observed = daily.index[(daily["count"] == 1440) & (daily["size"] == 1440)]
    chosen_date = fully_observed[0] if len(fully_observed) else daily.index[0]
    part = candidate.loc[candidate["timestamp"].dt.normalize().eq(chosen_date)]
    fig, axis = plt.subplots(figsize=(11, 4))
    axis.plot(part["timestamp"], part["Global_active_power"], linewidth=0.8)
    axis.set(title=f"Активная мощность — {chosen_date:%d.%m.%Y}",
             xlabel="Время суток, ч:мин", ylabel="Средняя за минуту мощность, кВт")
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_missing_week(minutes, output: Path) -> None:
    """Неделя вокруг наиболее длительного пропуска (либо первая неделя)."""
    gaps = missing_runs(minutes)
    center = (gaps.iloc[0]["start"] + (gaps.iloc[0]["end"] - gaps.iloc[0]["start"]) / 2) if len(gaps) else minutes["timestamp"].min()
    begin = max(minutes["timestamp"].min(), center - pd.Timedelta(days=3.5))
    end = min(minutes["timestamp"].max(), begin + pd.Timedelta(days=7))
    part = minutes.loc[minutes["timestamp"].between(begin, end)].copy()
    fig, (power_axis, gap_axis) = plt.subplots(2, 1, sharex=True, figsize=(12, 6),
                                               gridspec_kw={"height_ratios": [3, 1]})
    power_axis.plot(part["timestamp"], part["Global_active_power"], linewidth=0.7)
    gap_axis.step(part["timestamp"], (~part["valid_Global_active_power"]).astype(int), where="post", color="tab:red")
    power_axis.set(ylabel="Мощность, кВт", title="Минутные измерения около длительного пропуска")
    gap_axis.set(xlabel="Дата", ylabel="Пропуск", yticks=[0, 1], ylim=(-0.2, 1.2))
    gap_axis.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    power_axis.grid(alpha=0.25)
    gap_axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_month_comparison(minutes, output: Path) -> None:
    """Сравнение исходных поминутных графиков полного и неполного месяцев."""
    coverage = monthly_coverage(minutes)
    available = set(coverage["month"])
    if {"2008-09", "2010-08"}.issubset(available):
        months = ["2008-09", "2010-08"]
    else:
        ordered = coverage.sort_values("coverage_record_pct", ascending=False)
<<<<<<< HEAD
        months = [ordered.iloc[0]["month"], ordered.iloc[-1]["month"]]
    fig, axes = plt.subplots(2, 1, figsize=(12, 6))
    period_index = minutes["timestamp"].dt.to_period("M")
    for axis, month in zip(axes, months):
=======
        months = list(dict.fromkeys([ordered.iloc[0]["month"], ordered.iloc[-1]["month"]]))
    fig, axes = plt.subplots(len(months), 1, figsize=(12, 3.5 * len(months)), squeeze=False)
    period_index = minutes["timestamp"].dt.to_period("M")
    for axis, month in zip(axes.flat, months):
>>>>>>> 2d58bc45e57904272e3a30d5b66a02aefca628c0
        part = minutes.loc[period_index.eq(pd.Period(month))]
        axis.plot(part["timestamp"], part["Global_active_power"], linewidth=0.4)
        axis.set(title=f"{month}: исходная минутная мощность", ylabel="Мощность, кВт")
        axis.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_hourly(hourly, output: Path) -> None:
    fig, axis = plt.subplots(figsize=(11, 5))
    for month, group in hourly.groupby("month"):
        axis.plot(group["hour"], group["mean_kw"], marker="o", markersize=2, label=month)
    axis.set(xlabel="Начало часа суток", ylabel="Средняя активная мощность, кВт",
             title="Средняя мощность по часам суток", xlim=(0, 23))
    axis.grid(alpha=0.25)
    axis.legend()
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_missing_experiment(experiment, output: Path) -> None:
    """Показывает и исходные профили, и отклонения, скрытые наложением линий.

    Скользящее среднее используется только для наглядности на нижней панели;
    исходные данные и численные показатели погрешности не сглаживаются.
    """
    profiles = experiment.pivot(index="minute_of_day", columns="scenario", values="mean_kw").sort_index()
    required = {"original", "random", "continuous"}
    if not required.issubset(profiles.columns):
        raise ValueError(f"Не найдены сценарии эксперимента: {sorted(required - set(profiles.columns))}")

    hours = profiles.index.to_numpy() / 60
    baseline = profiles["original"]
    fig, (power_axis, difference_axis) = plt.subplots(
        2, 1, figsize=(13, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 2]},
    )
    styles = {
        "random": ("#D55E00", "Случайные пропуски", "--"),
        "continuous": ("#009E73", "Непрерывный пропуск", ":"),
    }
    for scenario, (color, label, line_style) in styles.items():
        power_axis.plot(hours, profiles[scenario], color=color, linewidth=0.9,
                        alpha=0.7, linestyle=line_style, label=label)
    # Эталон выводится поверх остальных кривых — он больше не исчезает за ними.
    power_axis.plot(hours, baseline, color="#17365D", linewidth=1.4,
                    label="Исходный профиль (без искусственных пропусков)", zorder=3)

    for scenario, (color, label, line_style) in styles.items():
        difference_kw = profiles[scenario] - baseline
        # Тонкая полупрозрачная линия — точное отличие каждой минуты суток.
        difference_axis.plot(hours, difference_kw, color=color, linewidth=0.65, alpha=0.28)
        # Толстая линия — скользящее среднее только для визуального выделения тренда.
<<<<<<< HEAD
        visible_difference = difference_kw.rolling(15, center=True, min_periods=8).mean()
=======
        # Суточный профиль циклический: окно не обрывается на границе суток.
        pad = 7
        circular = pd.concat([difference_kw.iloc[-pad:], difference_kw,
                              difference_kw.iloc[:pad]], ignore_index=True)
        visible_difference = circular.rolling(15, center=True, min_periods=8).mean().iloc[
            pad:pad + len(difference_kw)
        ].to_numpy()
>>>>>>> 2d58bc45e57904272e3a30d5b66a02aefca628c0
        mae_kw = difference_kw.abs().mean()
        difference_axis.plot(hours, visible_difference, color=color, linestyle=line_style,
                             linewidth=2, label=f"{label}, MAE = {mae_kw:.3f} кВт")

    month = experiment["month"].iloc[0] if "month" in experiment else ""
    power_axis.set(title=f"Влияние пропусков на суточный профиль — {month}",
                   ylabel="Средняя активная мощность, кВт")
    power_axis.legend(loc="upper left", fontsize=9)
    difference_axis.axhline(0, color="0.25", linewidth=0.9)
    difference_axis.set(xlabel="Время суток, ч",
                        ylabel="Разность с исходным профилем, кВт", xlim=(0, 24),
                        title="Отклонения: тонкие линии — исходные; толстые — среднее за 15 минут")
    difference_axis.legend(loc="upper left", fontsize=9)
    difference_axis.set_xticks(np.arange(0, 25, 2))
    for axis in (power_axis, difference_axis):
        axis.grid(alpha=0.22)
    fig.tight_layout()
    fig.savefig(output, dpi=250, bbox_inches="tight")
    plt.close(fig)


<<<<<<< HEAD
=======
def plot_missing_sensitivity(trials: pd.DataFrame, output: Path) -> None:
    """Показывает эмпирический разброс ошибок при разных расположениях пропусков."""
    groups = [trials.loc[trials["scenario"].eq(name), "mae_kw"].dropna().to_numpy()
              for name in ("random", "continuous")]
    fig, axis = plt.subplots(figsize=(10, 5.5))
    axis.boxplot(groups, widths=0.45, showmeans=True,
                 medianprops={"color": "#17365D", "linewidth": 1.7})
    colors = ("#D55E00", "#009E73")
    rng = np.random.default_rng(42)  # только распределение точек по горизонтали
    for index, (values, color) in enumerate(zip(groups, colors), start=1):
        axis.scatter(rng.normal(index, 0.045, len(values)), values,
                     s=13, alpha=0.28, color=color, zorder=2)
    axis.set_xticks([1, 2], ["Случайные пропуски", "Непрерывный пропуск"])
    axis.set(title="Зависимость ошибки от расположения 10% пропусков",
             ylabel="MAE суточного профиля, кВт")
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


>>>>>>> 2d58bc45e57904272e3a30d5b66a02aefca628c0
def plot_complete_days(profiles, output: Path) -> None:
    available_months = profiles["month"].unique().tolist()
    focus_months = [month for month in ("2009-08", "2010-08") if month in available_months]
    months = focus_months if focus_months else available_months[:4]
    fig, axes = plt.subplots(len(months), 1, figsize=(11, 3.5 * len(months)), squeeze=False)
    for axis, month in zip(axes.flat, months):
        group = profiles.loc[profiles["month"].eq(month)]
        time_hours = group["minute_of_day"] / 60
        axis.plot(time_hours, group["all_observations_kw"], label="Все измерения")
<<<<<<< HEAD
        axis.plot(time_hours, group["complete_days_kw"], label="Только полные сутки")
=======
        if group["complete_days_kw"].notna().any():
            axis.plot(time_hours, group["complete_days_kw"], label="Только полные сутки")
        else:
            axis.text(0.5, 0.92, "В этом месяце нет полных суток: сравнение невозможно",
                      transform=axis.transAxes, ha="center", va="top", fontsize=9)
>>>>>>> 2d58bc45e57904272e3a30d5b66a02aefca628c0
        axis.set(title=month, ylabel="Мощность, кВт")
        axis.grid(alpha=0.25)
        axis.legend()
    axes.flat[-1].set_xlabel("Время суток, ч")
    fig.tight_layout()
    fig.savefig(output, dpi=220)
    plt.close(fig)


def process_one(source: Path) -> Path:
    """Полный анализ одного файла. Другие файлы и исходные данные не трогает."""
    data = load_measurements(source)
    output = result_folder(source)
    output.mkdir(parents=True, exist_ok=True)
    save_csv(audit(data), output / "01_audit.csv")
    minutes = regular_minutes(data)
    save_csv(monthly_coverage(minutes), output / "02_monthly_coverage.csv")
    save_csv(missing_runs(minutes), output / "02_missing_runs.csv")
    energy = convert_energy(minutes)
    energy_cols = [col for col in energy.columns if col == "timestamp" or col.endswith("_kwh")]
    save_csv(energy[energy_cols], output / "03_energy_kwh.csv")
    save_csv(monthly_statistics(minutes), output / "05_monthly_statistics.csv")

    selected_months = select_months(minutes)
    profiles = daily_profiles(minutes, selected_months)
    save_csv(profiles, output / "04_daily_profiles.csv")
    save_csv(hourly_profiles(minutes, selected_months), output / "05_hourly_profiles.csv")
    save_csv(export_labplot(profiles), output / "04_labplot_profiles.csv")
    plot_profiles(profiles, output / "04_daily_profiles.png")
    plot_one_day(minutes, output / "04_one_day.png")
    plot_missing_week(minutes, output / "04_missing_week.png")
    plot_month_comparison(minutes, output / "04_month_comparison.png")
    plot_hourly(hourly_profiles(minutes, selected_months), output / "05_hourly_profiles.png")

    smoothed, comparison = smooth_profiles(profiles)
    save_csv(smoothed, output / "05_smoothed_profiles.csv")
    save_csv(comparison, output / "05_smoothing_metrics.csv")
    plot_smoothing(smoothed, output / "05_smoothing.png")

    incomplete_months = monthly_coverage(minutes).loc[
        lambda frame: frame["missing_or_invalid"].gt(0), "month"
    ].tolist()
    if incomplete_months:
        full_day_profiles, full_day_metrics = compare_complete_days(minutes, incomplete_months)
        save_csv(full_day_profiles, output / "05_complete_day_profiles.csv")
        save_csv(full_day_metrics, output / "05_complete_day_metrics.csv")
        plot_complete_days(full_day_profiles, output / "05_complete_day_profiles.png")
    experiment_profiles, experiment_metrics = missing_experiment(minutes)
    if not experiment_profiles.empty:
        save_csv(experiment_profiles, output / "05_missing_experiment_profiles.csv")
        save_csv(experiment_metrics, output / "05_missing_experiment_metrics.csv")
        plot_missing_experiment(experiment_profiles, output / "05_missing_experiment.png")
<<<<<<< HEAD
=======
        robustness_trials, robustness_summary = missing_experiment_robustness(minutes)
        save_csv(robustness_trials, output / "05_missing_robustness_trials.csv")
        save_csv(robustness_summary, output / "05_missing_robustness_summary.csv")
        plot_missing_sensitivity(robustness_trials, output / "05_missing_robustness.png")
    save_run_metadata(source, output, {
        "selected_months": selected_months,
        "missing_fraction": 0.1, "random_seed": 2026,
        "random_repetitions": 100,
        "block_placement": "nearest_midnight_to_month_center; all_midnights_for_robustness",
    })
>>>>>>> 2d58bc45e57904272e3a30d5b66a02aefca628c0
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Анализ всех файлов поминутного электропотребления в репозитории")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true", help="Обработать каждый файл из data/raw")
    mode.add_argument("--file", type=Path, help="Обработать конкретный файл из репозитория")
    args = parser.parse_args()
    sources = input_files() if args.all else [choose_source(args.file)]
    errors = 0
    for source in sources:
        print(f"Анализ: {source.relative_to(REPO_ROOT) if source.is_relative_to(REPO_ROOT) else source}")
        try:
            output = process_one(source)
            print(f"Готово: {output}")
        except (ValueError, FileNotFoundError, AssertionError, OSError) as exc:
            errors += 1
            print(f"ОШИБКА ({source.name}): {exc}", file=sys.stderr)
    print(f"Обработано: {len(sources) - errors} из {len(sources)}; ошибок: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

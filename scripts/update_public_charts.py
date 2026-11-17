"""Перестроить опубликованный рисунок пропусков по сохранённым CSV.

Запуск из корня репозитория: python scripts/update_public_charts.py
Исходные измерения UCI повторно читать не требуется.
"""

import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from run_analysis import plot_missing_experiment  # noqa: E402


def main():
    source = REPO_ROOT / "статистические результаты" / "05_профили_с_пропусками.csv"
    legacy = pd.read_csv(source, sep=";", encoding="utf-8-sig")
    scenario_columns = {
        "original": "P_Полный_кВт",
        "random": "P_Случайный_кВт",
        "continuous": "P_Длительный_кВт",
    }
    profiles = pd.concat([
        pd.DataFrame({
            "month": "2008-09",
            "scenario": scenario,
            "minute_of_day": legacy["Минута"],
            "mean_kw": legacy[column],
        })
        for scenario, column in scenario_columns.items()
    ], ignore_index=True)
    destination = REPO_ROOT / "графики" / "05_влияние_пропусков.png"
    plot_missing_experiment(profiles, destination)
    print(f"Рисунок обновлён: {destination}")


if __name__ == "__main__":
    main()

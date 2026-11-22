"""Синхронизирует отобранные опубликованные результаты с полным расчётом UCI.

Сначала выполните `python run_analysis.py --all`, затем этот скрипт.
Новые наборы данных остаются в собственных папках `результаты/` и не
подменяют опубликованные рисунки исследования 2008 года.
"""

from pathlib import Path
import shutil
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from ipd_analysis import result_folder  # noqa: E402


PUBLIC_FILES = {
    "05_missing_experiment.png": "графики/05_влияние_пропусков.png",
    "05_missing_robustness.png": "графики/05_устойчивость_к_пропускам.png",
    "05_missing_robustness_trials.csv": "статистические результаты/05_устойчивость_сценарии.csv",
    "05_missing_robustness_summary.csv": "статистические результаты/05_устойчивость_сводка.csv",
}


def main() -> None:
    source = REPO_ROOT / "data/raw/household_power_consumption.zip"
    computed = result_folder(source)
    missing = [name for name in PUBLIC_FILES if not (computed / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Сначала выполните python run_analysis.py --all; отсутствуют: " + ", ".join(missing)
        )
    for source_name, relative_destination in PUBLIC_FILES.items():
        destination = REPO_ROOT / relative_destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(computed / source_name, destination)
        print(f"Опубликовано: {destination.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

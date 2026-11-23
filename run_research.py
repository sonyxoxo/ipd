"""One entry point for existing exploratory analysis and enhanced science stages.

Usage:
  python run_research.py --all
  python run_research.py --all --skip-core --publish
  python run_research.py --file data/raw/household_power_consumption.zip
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import sys

import numpy as np
import pandas as pd
import matplotlib

from ipd_analysis import input_files, choose_source, load_measurements, regular_minutes, result_folder
from ipd_science import run_science, write_manifest, source_quality_report
from run_analysis import process_one

ROOT = Path(__file__).resolve().parent


def hash_file(file: Path) -> str:
    digest = sha256()
    with file.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def handle(source: Path, args) -> Path:
    if not args.skip_core:
        process_one(source)
    measured = load_measurements(source)
    minutes = regular_minutes(measured)
    out = result_folder(source) / "этап_06_v2"
    out.mkdir(parents=True, exist_ok=True)
    source_quality_report(measured, out)
    result = run_science(minutes, out, h2_repetitions=args.h2_repetitions,
                         h3_repetitions=args.h3_repetitions,
                         gap_repetitions=args.gap_repetitions,
                         h1_permutations=args.permutations)
    provenance = {
        "source": str(source.resolve().relative_to(ROOT.resolve())) if source.is_relative_to(ROOT) else str(source),
        "source_sha256": hash_file(source),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "numpy": np.__version__,
        "pandas": pd.__version__, "matplotlib": matplotlib.__version__,
        "code_sha256": {name: hash_file(ROOT/name) for name in
                        ("ipd_analysis.py", "ipd_science.py", "run_research.py")},
        "parameters": {"h2_repetitions": args.h2_repetitions,
                       "h3_repetitions": args.h3_repetitions,
                       "gap_repetitions": args.gap_repetitions,
                       "h1_permutations": args.permutations,
                       "gap_lengths_minutes": [1, 5, 15, 30, 60, 120],
                       "fractions_h2": [.01, .05, .10, .20],
                       "block_days_h1": [3, 5, 7],
                       "seed_h1_h2": 2026, "seed_h3": 2027},
        "scientific_report": result,
    }
    (out / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    write_manifest(out)
    from scripts.verify_results import verify_directory
    verify_directory(out)
    if args.publish:
        published = ROOT / "статистические результаты" / "актуальные_v2"
        images = ROOT / "графики" / "актуальные_v2"
        published.mkdir(parents=True, exist_ok=True)
        images.mkdir(parents=True, exist_ok=True)
        for item in out.iterdir():
            if item.suffix.lower() in (".csv", ".json"):
                shutil.copy2(item, published / item.name)
            elif item.suffix.lower() == ".png":
                shutil.copy2(item, images / item.name)
        print("Опубликованы новые результаты:", published, "и", images)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="IPD: воспроизводимый полный анализ")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--all", action="store_true")
    source.add_argument("--file", type=Path)
    parser.add_argument("--skip-core", action="store_true", help="Не повторять неизменённые этапы 1–5")
    parser.add_argument("--publish", action="store_true", help="Опубликовать подтверждённые CSV/PNG отдельно от архивных")
    parser.add_argument("--h2-repetitions", type=int, default=100)
    parser.add_argument("--h3-repetitions", type=int, default=30)
    parser.add_argument("--gap-repetitions", type=int, default=15)
    parser.add_argument("--permutations", type=int, default=999)
    args = parser.parse_args()
    if any(n < 1 for n in (args.h2_repetitions, args.h3_repetitions,
                            args.gap_repetitions, args.permutations)):
        parser.error("Все числа повторений должны быть положительными")
    sources = input_files() if args.all else [choose_source(args.file)]
    errors = []
    for source_file in sources:
        try:
            p = handle(source_file, args)
            print("Успешно:", source_file, "→", p)
        except Exception as err:
            print("ОШИБКА:", source_file, str(err), file=sys.stderr)
            errors.append(source_file)
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())

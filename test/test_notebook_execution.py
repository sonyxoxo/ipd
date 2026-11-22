"""Интеграционный запуск всех кодовых ячеек пяти Jupyter-ноутбуков.

Выполняется в отдельном Python-процессе с временным клоном и поминутным
синтетическим CSV. Интерфейс Colab, сеть и вручную загруженные файлы не нужны.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]


class AllNotebooksTest(unittest.TestCase):
    def test_every_code_cell_executes_from_temporary_repository(self):
        with tempfile.TemporaryDirectory(prefix="ipd-notebooks-") as location:
            project = Path(location)
            notebooks_dir = project / "ноутбуки python"
            notebooks_dir.mkdir()
            (project / "data/raw").mkdir(parents=True)
            for name in ("ipd_analysis.py", "run_analysis.py", "analysis_config.json"):
                shutil.copy2(REPO_ROOT / name, project / name)
            for notebook in (REPO_ROOT / "ноутбуки python").glob("*.ipynb"):
                shutil.copy2(notebook, notebooks_dir / notebook.name)

            dates = pd.date_range("2024-01-01", periods=31 * 1440 + 1000, freq="min")
            hours = np.asarray(dates.hour) + np.asarray(dates.minute) / 60
            power = 1.5 + 0.4 * np.sin(2 * np.pi * hours / 24)
            power[31 * 1440 + 17] = np.nan
            pd.DataFrame({
                "timestamp": dates, "Global_active_power": power,
                "Voltage": 230, "Sub_metering_1": 17,
            }).to_csv(project / "data/raw/measurements.csv", sep=";", index=False)

            interpreter = '''import json
from pathlib import Path
notebooks = sorted(Path.cwd().glob("*.ipynb"))
for file in notebooks:
    context = {"__name__": "__main__", "display": lambda *args, **kwargs: None}
    notebook = json.loads(file.read_text(encoding="utf-8"))
    for index, cell in enumerate(notebook["cells"], 1):
        if cell["cell_type"] == "code":
            exec(compile("".join(cell["source"]), f"{file.name}:cell{index}", "exec"), context)
    print("PASS", file.name)
assert len(notebooks) == 5
'''
            completed = subprocess.run(
                [sys.executable, "-c", interpreter], cwd=notebooks_dir,
                capture_output=True, text=True, timeout=180, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-4000:])
            self.assertEqual(completed.stdout.count("PASS "), 5, completed.stdout[-1500:])
            results = list((project / "результаты").glob("*/metadata.json"))
            self.assertEqual(len(results), 1)
            metadata = json.loads(results[0].read_text(encoding="utf-8"))
            self.assertTrue(metadata["source_sha256"])
            self.assertTrue((results[0].parent / "05_missing_robustness.png").is_file())


if __name__ == "__main__":
    unittest.main()

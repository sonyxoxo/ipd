"""Автоматические проверки структуры данных и ключевых расчётов."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile
import json
import io
import tokenize

import numpy as np
import pandas as pd

import ipd_analysis as analysis
from run_analysis import process_one, plot_missing_experiment


class ElectricityAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def sample_file(self, filename="sample.txt"):
        file_path = self.directory / filename
        file_path.write_text(
            "Date;Time;Global_active_power;Voltage;Sub_metering_1\n"
            "31/01/2024;23:58:00;2;230;17\n"
            "31/01/2024;23:59:00;?;230;?\n"
            "01/02/2024;00:01:00;4;230;15\n"
            "01/02/2024;00:02:00;-3;230;16\n",
            encoding="utf-8",
        )
        return file_path

    def test_time_gaps_cross_months_and_energy(self):
        data = analysis.load_measurements(self.sample_file())
        self.assertEqual(len(data), 4)
        minutes = analysis.regular_minutes(data)
        self.assertEqual(len(minutes), 5)
        self.assertEqual(int(minutes["Global_active_power"].isna().sum()), 3)
        coverage = analysis.monthly_coverage(minutes)
        self.assertEqual(coverage["valid_power"].tolist(), [1, 1])
        self.assertEqual(coverage["expected_in_record"].tolist(), [2, 3])
        runs = analysis.missing_runs(minutes)
        self.assertEqual(int(runs.iloc[0]["minutes"]), 2)
        self.assertTrue(bool(runs.iloc[0]["crosses_month"]))
        energy = analysis.convert_energy(minutes)
        self.assertAlmostEqual(energy["active_energy_kwh"].iloc[0], 2 / 60)
        self.assertAlmostEqual(energy["sub_1_energy_kwh"].iloc[0], 0.017)
        self.assertTrue(np.isnan(energy["active_energy_kwh"].iloc[-1]))

    def test_zip_loading_and_discovery(self):
        sample = self.sample_file()
        archive_path = self.directory / "input.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(sample, arcname="household_power_consumption.txt")
        with patch.object(analysis, "RAW_DIR", self.directory):
            self.assertEqual(len(analysis.input_files(self.directory)), 2)
        data = analysis.load_measurements(archive_path)
        self.assertEqual(len(data), 4)

    def test_duplicate_time_rejected(self):
        path = self.sample_file()
        with path.open("a", encoding="utf-8") as stream:
            stream.write("31/01/2024;23:58:00;2;230;17\n")
        data = analysis.load_measurements(path)
        self.assertEqual(int(analysis.audit(data)["duplicate_timestamps"].iloc[0]), 1)
        with self.assertRaisesRegex(ValueError, "повторяются"):
            analysis.regular_minutes(data)

    def test_missing_required_column_rejected(self):
        path = self.directory / "wrong.csv"
        path.write_text("timestamp;temperature\n2024-01-01 00:00;20\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Global_active_power"):
            analysis.load_measurements(path)

    def test_non_minute_sampling_rejected(self):
        path = self.directory / "quarter_hour.csv"
        stamps = pd.date_range("2024-01-01", periods=20, freq="15min")
        pd.DataFrame({"timestamp": stamps, "Global_active_power": 2.0}).to_csv(
            path, sep=";", index=False
        )
        data = analysis.load_measurements(path)
        with self.assertRaisesRegex(ValueError, "не каждую минуту"):
            analysis.regular_minutes(data)

    def test_full_pipeline_for_small_file(self):
        source = self.sample_file("dataset.csv")
        with patch.object(analysis, "RESULTS_DIR", self.directory / "results"):
            output = process_one(source)
        self.assertTrue((output / "01_audit.csv").exists())
        self.assertTrue((output / "02_missing_runs.csv").exists())
        self.assertTrue((output / "03_energy_kwh.csv").exists())
        self.assertTrue((output / "04_daily_profiles.png").exists())
        self.assertTrue((output / "05_monthly_statistics.csv").exists())
        self.assertTrue(source.read_text(encoding="utf-8").startswith("Date;Time;"))

    def test_notebooks_have_latin_identifiers_and_no_uploads(self):
        notebooks = list((analysis.REPO_ROOT / "ноутбуки python").glob("*.ipynb"))
        self.assertEqual(len(notebooks), 6)
        for path in notebooks:
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell["cell_type"] != "code":
                    continue
                source = "".join(cell["source"])
                compile(source, str(path), "exec")
                self.assertNotIn("files.upload", source)
                names = [
                    token.string for token in tokenize.generate_tokens(io.StringIO(source).readline)
                    if token.type == tokenize.NAME and not token.string.isascii()
                ]
                self.assertEqual(names, [], f"Кириллические идентификаторы в {path.name}")

    def test_missing_experiment_plot_does_not_modify_source(self):
        times = np.arange(60)
        table = pd.concat([
            pd.DataFrame({
                "month": "2024-01", "scenario": scenario,
                "minute_of_day": times, "mean_kw": values,
            })
            for scenario, values in {
                "original": np.ones(60),
                "random": np.ones(60) + np.sin(times / 5) * 0.03,
                "continuous": np.ones(60) + np.cos(times / 9) * 0.04,
            }.items()
        ], ignore_index=True)
        original_copy = table.copy(deep=True)
        output = self.directory / "missing_plot.png"
        plot_missing_experiment(table, output)
        self.assertGreater(output.stat().st_size, 5000)
        pd.testing.assert_frame_equal(table, original_copy)


if __name__ == "__main__":
    unittest.main()

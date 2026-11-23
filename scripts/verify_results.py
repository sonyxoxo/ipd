"""Verify a generated v2 run against its independent summary recomputation.

It validates saved tables and their checksums. This is not an independent
statistical inference or a substitute for rerunning the raw-data pipeline.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd


def verify_directory(directory: Path) -> dict:
    directory = Path(directory)
    manifest_path = directory / "manifest_sha256.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, digest in manifest.items():
            actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
            if actual != digest:
                raise AssertionError(f"Changed output since run: {name}")
    checks = {}
    for pair in (("06_h2_trials.csv", "06_h2_summary.csv", ["fraction", "scenario"]),
                 ("06_h3_trials.csv", "06_h3_summary.csv", ["scenario", "method"]),
                 ("06_h3_gap_trials.csv", "06_h3_gap_summary.csv", ["gap_length", "method"])):
        a, b, keys = pair
        if not (directory / a).exists():
            continue
        trials = pd.read_csv(directory / a, sep=";")
        summary = pd.read_csv(directory / b, sep=";")
        recomputed = trials.groupby(keys, as_index=False)["mae_kw"].mean().rename(columns={"mae_kw": "mean_mae_kw"})
        check = summary.merge(recomputed, on=keys, suffixes=("_reported", "_recomputed"), validate="one_to_one")
        if len(check) != len(summary):
            raise AssertionError(f"Missing groups in {b}")
        observed, expected = check.mean_mae_kw_reported.to_numpy(), check.mean_mae_kw_recomputed.to_numpy()
        if not np.allclose(observed, expected, atol=1e-8, rtol=0, equal_nan=True):
            raise AssertionError(f"Summary mismatch: {b}")
        checks[b] = "verified"
    return checks

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", type=Path)
    args = ap.parse_args()
    print(verify_directory(args.directory))

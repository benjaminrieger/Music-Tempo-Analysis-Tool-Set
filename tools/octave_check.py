#!/usr/bin/env python3
"""
octave_check.py: compare algorithm tempi with hand taps and correct octave errors.

The hand tap is treated as the reference for the metrical level (which pulse is
the beat), not as a precise tempo. For each file, the ratio
    algorithm BPM / tapped BPM
is assigned to the nearest of 1:3, 1:2, 2:3, 1:1, 3:2, 2:1, 3:1 (on a log scale).
  - nearest 2:1 -> algorithm counted double time  -> corrected BPM = algorithm / 2
  - nearest 1:2 -> algorithm counted half time    -> corrected BPM = algorithm * 2
  - nearest 3:1 or 1:3 -> flagged for manual review (not corrected automatically)
  - anything else -> unchanged
Clips marked "skipped" in the tapping tool are listed as excluded.

Inputs
  --summary  CSV from vocal_tempo.py (columns Filename, Reported_BPM), or any CSV
             with a filename column and a BPM column (set --summary-file-col / --summary-bpm-col)
  --taps     CSV exported from tools/tempo_tapper.html (filename, tapped_bpm, pass, skipped)

Output
  octave_check.csv with one row per file: algorithm BPM, tapped BPM, ratio,
  nearest relation, deviation from that exact ratio, action, corrected BPM.

    python tools/octave_check.py --summary audio/tempo_summary_generic.csv --taps tempo_taps_XX.csv
"""

import argparse
import sys

import numpy as np
import pandas as pd

RELATIONS = {"1:3": 1 / 3, "1:2": 1 / 2, "2:3": 2 / 3, "1:1": 1.0, "3:2": 3 / 2, "2:1": 2.0, "3:1": 3.0}


def nearest_relation(ratio):
    k = min(RELATIONS, key=lambda r: abs(np.log(ratio / RELATIONS[r])))
    return k, abs(ratio / RELATIONS[k] - 1)


def run(summary, taps, file_col="Filename", bpm_col="Reported_BPM", clear_tol=0.08):
    s = summary[[file_col, bpm_col]].rename(columns={file_col: "filename", bpm_col: "algorithm_bpm"})
    s["algorithm_bpm"] = pd.to_numeric(s["algorithm_bpm"], errors="coerce")

    t = taps.copy()
    if "pass" in t.columns:  # use first-pass taps as the reference; keep the latest per file
        t = t[pd.to_numeric(t["pass"], errors="coerce").fillna(1) == 1]
    if "tapped_iso" in t.columns:
        t = t.sort_values("tapped_iso")
    t = t.drop_duplicates("filename", keep="last")
    t["skipped"] = t.get("skipped", 0).astype(str).isin(["1", "true", "True"])
    t["tapped_bpm"] = pd.to_numeric(t["tapped_bpm"], errors="coerce")

    m = s.merge(t[["filename", "tapped_bpm", "skipped"]], on="filename", how="left")
    out = []
    for _, r in m.iterrows():
        row = {"filename": r.filename, "algorithm_bpm": r.algorithm_bpm, "tapped_bpm": r.tapped_bpm}
        if pd.isna(r.skipped):
            row.update(action="no tap", corrected_bpm=r.algorithm_bpm)
        elif r.skipped:
            row.update(action="excluded (skipped while tapping)", corrected_bpm=np.nan)
        elif pd.isna(r.algorithm_bpm) or pd.isna(r.tapped_bpm) or r.tapped_bpm <= 0:
            row.update(action="missing value", corrected_bpm=r.algorithm_bpm)
        else:
            ratio = r.algorithm_bpm / r.tapped_bpm
            rel, dev = nearest_relation(ratio)
            row.update(ratio=ratio, nearest=rel, deviation=dev,
                       tier="clear" if dev <= clear_tol else "borderline")
            if rel == "2:1":
                row.update(action="halved", corrected_bpm=r.algorithm_bpm / 2)
            elif rel == "1:2":
                row.update(action="doubled", corrected_bpm=r.algorithm_bpm * 2)
            elif rel in ("3:1", "1:3"):
                row.update(action="review (triple relation)", corrected_bpm=r.algorithm_bpm)
            else:
                row.update(action="unchanged", corrected_bpm=r.algorithm_bpm)
        out.append(row)
    cols = ["filename", "algorithm_bpm", "tapped_bpm", "ratio", "nearest", "deviation", "tier",
            "action", "corrected_bpm"]
    return pd.DataFrame(out).reindex(columns=cols)


def main(argv=None):
    p = argparse.ArgumentParser(description="Octave check of algorithm tempi against hand taps.")
    p.add_argument("--summary", required=True)
    p.add_argument("--taps", required=True)
    p.add_argument("--summary-file-col", default="Filename")
    p.add_argument("--summary-bpm-col", default="Reported_BPM")
    p.add_argument("--out", default="octave_check.csv")
    a = p.parse_args(argv)
    res = run(pd.read_csv(a.summary), pd.read_csv(a.taps), a.summary_file_col, a.summary_bpm_col)
    res.to_csv(a.out, index=False)
    print(res["action"].value_counts().to_string())
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    sys.exit(main())

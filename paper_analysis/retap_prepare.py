#!/usr/bin/env python3
"""
Intra-rater check, step 1: draw 50 random recordings and copy them into a new folder.

The sample is drawn from the recordings included in the analysis (Tempo_Corrected.xlsx,
sheet "All clips", status Included, countries in EXCLUDE_COUNTRIES left out), with a fixed
seed, so it is reproducible. The files are copied into 01_data/retest_50. Open that folder
in tools/tempo_tapper.html: the tapper keeps its progress per folder name, so the earlier
taps are not shown, and the order is randomised.

Run from 02_code:
    python retap_prepare.py
Then tap the folder in the tapper with rater initials BR2 and export the CSV into 01_data.
"""

import os
import shutil
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "01_data")
TEMPO_XLSX = os.path.join(PROJECT, "03_output", "Tempo_Corrected.xlsx")
RECORDINGS = os.path.join(DATA, "recordings_pcm")   # the folder you tapped originally
OUT_FOLDER = os.path.join(DATA, "retest_50")
LIST_CSV = os.path.join(DATA, "retest_50_list.csv")
N = 50
SEED = 50
EXCLUDE_COUNTRIES = ["Australia"]
# ---------------------------------------------------------------------------


def sample():
    clips = pd.read_excel(TEMPO_XLSX, sheet_name="All clips")
    clips = clips[clips["status"] == "Included"].copy()
    for c in EXCLUDE_COUNTRIES:
        clips = clips[~clips["filename"].str.contains("_" + c.replace(" ", "_") + "_", regex=False)]
    clips = clips.sort_values("filename").reset_index(drop=True)
    rng = np.random.default_rng(SEED)
    pick = np.sort(rng.choice(len(clips), size=N, replace=False))
    return clips.iloc[pick][["filename", "song_type"]].reset_index(drop=True), len(clips)


def main():
    s, pool = sample()
    s[["filename"]].to_csv(LIST_CSV, index=False)
    print(f"Drew {N} of {pool} included recordings (seed {SEED}).")
    print(s["song_type"].value_counts().to_string())
    print(f"List saved: {LIST_CSV}")

    if not os.path.isdir(RECORDINGS):
        sys.exit(f"\nRecordings folder not found: {RECORDINGS}\nSet RECORDINGS at the top of this script and run again.")
    os.makedirs(OUT_FOLDER, exist_ok=True)
    missing = []
    for f in s["filename"]:
        src = os.path.join(RECORDINGS, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OUT_FOLDER, f))
        else:
            missing.append(f)
    print(f"Copied {N - len(missing)} files to {OUT_FOLDER}")
    if missing:
        print("Not found:", *missing, sep="\n  ")


if __name__ == "__main__":
    main()

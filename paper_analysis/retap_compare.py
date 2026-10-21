#!/usr/bin/env python3
"""
Inter-rater check, step 2: compare the second rater's taps of the 50 recordings with the first rater's.

What it reports
  1  Metrical level: in how many recordings the second rater taps the same metrical level
     as the first (ratio second/first nearest to 1:1 rather than 2:1, 1:2, 3:2, ...).
  2  Octave decision: whether the octave check (halve / double / keep), run with the second
     rater's tap instead of the first, reaches the same decision for each recording. This is the
     agreement that matters for the paper, because the tap only decides the metrical level.
  3  Tempo agreement: ICC(A,1) (two-way, absolute agreement, single measure; McGraw & Wong,
     1996) on log2 tapped BPM, with 95% CI, and the median absolute difference in percent.

Run from 02_code after the second rater's CSV export is in 01_data:
    python retap_compare.py
or name the file:  python retap_compare.py ..\\01_data\\tempo_taps_RP_....csv
"""

import glob
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(PROJECT, "01_data")
TEMPO_XLSX = os.path.join(PROJECT, "03_output", "Tempo_Corrected.xlsx")
LIST_CSV = os.path.join(DATA, "retest_50_list.csv")
OUT_TXT = os.path.join(PROJECT, "03_output", "retap_report.txt")
RATER2 = "RP"                       # initials the second rater entered in the tapper
RETAP_PATTERN = f"tempo_taps_{RATER2}_*.csv"
RELATIONS = {"1:3": 1 / 3, "1:2": 1 / 2, "2:3": 2 / 3, "1:1": 1.0, "3:2": 3 / 2, "2:1": 2.0, "3:1": 3.0}
# ---------------------------------------------------------------------------


def nearest(ratio):
    return min(RELATIONS, key=lambda r: abs(np.log(ratio / RELATIONS[r])))


def action(analysed, tap):
    rel = nearest(analysed / tap)
    return {"2:1": "halve", "1:2": "double", "3:1": "review", "1:3": "review"}.get(rel, "keep")


def icc_a1(x, y):
    """ICC(A,1) with 95% CI (McGraw & Wong, 1996, case 2A)."""
    M = np.column_stack([x, y]).astype(float)
    n, k = M.shape
    gm = M.mean()
    ssr = k * ((M.mean(1) - gm) ** 2).sum()
    ssc = n * ((M.mean(0) - gm) ** 2).sum()
    sse = ((M - gm) ** 2).sum() - ssr - ssc
    msr, msc, mse = ssr / (n - 1), ssc / (k - 1), sse / ((n - 1) * (k - 1))
    icc = (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)
    a = k * icc / (n * (1 - icc))
    b = 1 + k * icc * (n - 1) / (n * (1 - icc))
    v = (a * msc + b * mse) ** 2 / ((a * msc) ** 2 / (k - 1) + (b * mse) ** 2 / ((n - 1) * (k - 1)))
    fl = stats.f.ppf(0.975, n - 1, v)
    fu = stats.f.ppf(0.975, v, n - 1)
    lo = n * (msr - fl * mse) / (fl * (k * msc + (k * n - k - n) * mse) + n * msr)
    hi = n * (fu * msr - mse) / (k * msc + (k * n - k - n) * mse + n * fu * msr)
    return icc, lo, hi


def main():
    if len(sys.argv) > 1:
        retap_file = sys.argv[1]
    else:
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        found = sorted(glob.glob(os.path.join(DATA, RETAP_PATTERN)))
        if not found:   # the browser saves the export to Downloads by default
            found = sorted(glob.glob(os.path.join(downloads, RETAP_PATTERN)))
        if not found:
            sys.exit(f"No file matching {RETAP_PATTERN} in {DATA} or {downloads}.\n"
                     f"The second rater taps 01_data/retest_50 with initials {RATER2} and exports the CSV; "
                     f"or pass the file name: python retap_compare.py <path to csv>")
        retap_file = found[-1]
    clips = pd.read_excel(TEMPO_XLSX, sheet_name="All clips")
    sel = pd.read_csv(LIST_CSV)
    rt = pd.read_csv(retap_file)
    rt = rt[(rt.get("skipped", 0).astype(str) != "1") & rt["tapped_bpm"].notna()]
    rt = rt.sort_values("tapped_iso").drop_duplicates("filename", keep="last")

    d = sel.merge(clips[["filename", "song_type", "tapped_bpm", "analysed_bpm", "action"]], on="filename", how="left")
    d = d.merge(rt[["filename", "tapped_bpm"]].rename(columns={"tapped_bpm": "tap2"}), on="filename", how="left")
    d = d.rename(columns={"tapped_bpm": "tap1", "action": "action1"})
    d["tap1"] = pd.to_numeric(d["tap1"], errors="coerce")
    d["tap2"] = pd.to_numeric(d["tap2"], errors="coerce")
    d["analysed_bpm"] = pd.to_numeric(d["analysed_bpm"], errors="coerce")
    missing = d[d["tap2"].isna()]
    d = d[d["tap2"].notna() & d["tap1"].notna()].copy()

    d["level"] = [nearest(b / a) for a, b in zip(d["tap1"], d["tap2"])]
    d["same_level"] = d["level"] == "1:1"
    d["action2"] = [action(a, t) for a, t in zip(d["analysed_bpm"], d["tap2"])]
    d["action1_rule"] = [action(a, t) for a, t in zip(d["analysed_bpm"], d["tap1"])]
    d["same_action"] = d["action1_rule"] == d["action2"]
    d["abs_pct"] = (d["tap2"] / d["tap1"] - 1).abs() * 100

    n = len(d)
    icc, lo, hi = icc_a1(np.log2(d["tap1"]), np.log2(d["tap2"]))
    same = d[d["same_level"]]
    icc_s, lo_s, hi_s = icc_a1(np.log2(same["tap1"]), np.log2(same["tap2"])) if len(same) > 2 else (np.nan,) * 3

    out = []
    say = out.append
    say(f"Second rater ({RATER2}): {os.path.basename(retap_file)}")
    say(f"Recordings compared: {n} of {len(sel)}" + (f" ({len(missing)} skipped or missing for the second rater)" if len(missing) else ""))
    say("")
    say(f"1  Same metrical level for both raters: {d['same_level'].sum()} of {n} ({100 * d['same_level'].mean():.0f}%)")
    say("   Relation of second to first rater's tap: " + ", ".join(f"{k} {v}" for k, v in d["level"].value_counts().items()))
    say(f"2  Same octave decision (keep/halve/double): {d['same_action'].sum()} of {n} ({100 * d['same_action'].mean():.0f}%)")
    say(f"   Recordings in the sample corrected on the basis of the first rater's tap: {(d['action1_rule'] != 'keep').sum()}")
    say(f"3  ICC(A,1) on log2 tapped BPM, all recordings: {icc:.2f} [95% CI {lo:.2f}, {hi:.2f}]")
    say(f"   ICC(A,1), recordings tapped at the same level: {icc_s:.2f} [95% CI {lo_s:.2f}, {hi_s:.2f}], n = {len(same)}")
    say(f"   Median absolute difference at the same level: {same['abs_pct'].median():.1f}% "
        f"(IQR {same['abs_pct'].quantile(.25):.1f} to {same['abs_pct'].quantile(.75):.1f}%)")
    dis = d[~d["same_action"]]
    if len(dis):
        say("\nRecordings with a different octave decision:")
        for _, r in dis.iterrows():
            say(f"   {r.filename}: analysed {r.analysed_bpm:.1f}, rater 1 {r.tap1:.1f} ({r.action1_rule}), "
                f"rater 2 {r.tap2:.1f} ({r.action2})")
    say("\nDraft sentence for the paper (check the numbers above first):")
    say(f"   To assess the reliability of the tapping, {n} randomly selected recordings were tapped by a second "
        f"listener, a colleague with several years of musical experience as a rapper, with the same tool, blind to the first listener's taps, the software estimate, song type and "
        f"origin. The two listeners tapped the same metrical level in {d['same_level'].sum()} of {n} recordings, and the octave check reached the same decision in "
        f"{d['same_action'].sum()} of {n} recordings (ICC(A,1) on log tempo = {icc:.2f}, 95% CI [{lo:.2f}, {hi:.2f}]).")
    txt = "\n".join(out)
    print(txt)
    with open(OUT_TXT, "w", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    d.to_csv(os.path.join(PROJECT, "03_output", "retap_comparison.csv"), index=False)
    print(f"\nSaved: {OUT_TXT}")


if __name__ == "__main__":
    main()

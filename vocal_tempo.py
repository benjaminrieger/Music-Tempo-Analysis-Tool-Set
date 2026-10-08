#!/usr/bin/env python3
"""
vocal_tempo.py: tempo (BPM) estimation for unaccompanied singing, built on librosa.

The method combines two estimates from an onset-strength envelope:
  1. RBT  - robust beat-tracker tempo: librosa beat tracking, then 60 / median
            inter-beat interval. This is the reported value when available.
  2. ACF  - autocorrelation of the onset envelope, weighted by a Gaussian tempo
            prior and restricted to a tempo window. Used as a fallback.
Optional octave handling:
  - tactus correction: halve an estimate that lies closer to 2 x mu than to mu.
  - grid-fit octave check: for estimates above GRID_THRESHOLD, compare how well
    a beat grid at BPM and at BPM/2 aligns with the onset envelope and keep the
    better one (near ties go to the slower tempo).

Two presets are included:
  "generic"  - broad settings for singing of unknown tempo
  "lullaby"  - settings used in the cross-continental lullaby study
               (Rieger et al.; free singing, octave grid-fit on)
Every setting can be overridden. See docs/METHOD.md.

Usage, command line:
    python vocal_tempo.py path/to/audio_folder
    python vocal_tempo.py path/to/audio_folder --preset lullaby
    python vocal_tempo.py path/to/audio_folder --mu 100 --tmin 60 --tmax 180 --sigma 20

Usage, Python / Jupyter:
    import vocal_tempo as vt
    df = vt.analyze_folder("path/to/audio_folder", preset="lullaby")
    res = vt.analyze_file("song.wav", mu=90, tmin=50, tmax=160)

Author: Benjamin Rieger, TU Dresden (CeTI). License: MIT.
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

try:
    import librosa
except ImportError:  # allows importing the module for documentation without librosa
    librosa = None

__version__ = "1.0.0"

AUDIO_EXT = (".wav", ".mp3", ".flac", ".m4a", ".ogg")

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
PRESETS = {
    "generic": dict(
        mu=80.0,            # expected tempo centre (BPM) for the ACF prior and tactus correction
        sigma=5.0,          # width of the Gaussian prior (BPM); larger = less influence of mu
        tmin=40.0,          # lowest tempo the ACF may return (BPM)
        tmax=150.0,         # highest tempo the ACF may return (BPM)
        start_bpm=None,     # seed for librosa's beat tracker; None = use mu
        tactus=True,        # halve estimates that lie closer to 2*mu than to mu
        octave_grid=False,  # grid-fit check of BPM vs BPM/2 for fast estimates
        grid_threshold=95.0,
        hop=512,            # analysis hop (samples); ~11.6 ms at 44.1 kHz
        preemph=0.97,       # pre-emphasis coefficient; 0 disables
        smooth_frames=10,   # moving-average smoothing of the onset envelope (frames)
        sr=None,            # resample to this rate; None keeps the native rate
    ),
    "lullaby": dict(
        mu=60.0, sigma=5.0, tmin=40.0, tmax=100.0, start_bpm=60.0,
        tactus=True, octave_grid=True, grid_threshold=95.0,
        hop=512, preemph=0.97, smooth_frames=10, sr=None,
    ),
}


def settings(preset="generic", **overrides):
    if preset not in PRESETS:
        raise ValueError(f"Unknown preset {preset!r}. Choose from {list(PRESETS)}.")
    s = dict(PRESETS[preset])
    for k, v in overrides.items():
        if k not in s:
            raise ValueError(f"Unknown setting {k!r}. Valid settings: {list(s)}")
        if v is not None:
            s[k] = v
    if s["start_bpm"] is None:
        s["start_bpm"] = s["mu"]
    return s


# ---------------------------------------------------------------------------
# Signal processing
# ---------------------------------------------------------------------------
def _need_librosa():
    if librosa is None:
        raise ImportError("librosa is not installed. Run: python -m pip install -r requirements.txt")


def load_preemphasize(path, sr=None, preemph=0.97):
    _need_librosa()
    y, sr = librosa.load(path, sr=sr, mono=True)
    if preemph:
        y = librosa.effects.preemphasis(y, coef=preemph)
    return y, sr


def onset_envelope(y, sr, hop=512, smooth_frames=10):
    _need_librosa()
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    env = librosa.util.normalize(env)
    if smooth_frames and smooth_frames > 1:
        kernel = np.ones(smooth_frames) / smooth_frames
        env = np.convolve(env, kernel, mode="same")
    return env


def acf_unbiased(x):
    """Unbiased autocorrelation for lags 1 .. N//2 - 1 (FFT; same values as the direct sum)."""
    x = np.asarray(x, float)
    N = len(x)
    if N < 4:
        return np.array([])
    nfft = 1 << (2 * N - 1).bit_length()
    f = np.fft.rfft(x, nfft)
    full = np.fft.irfft(f * np.conj(f), nfft)[:N]
    k = np.arange(1, N // 2)
    return full[k] / (N - k)


def bpm_axis(sr, hop, length):
    lags = np.arange(1, length + 1)
    return 60.0 * sr / (hop * lags)


def acf_pick_tempo(onset_env, sr, hop, tempo_min, tempo_max, mu, sigma=5.0):
    acf = acf_unbiased(onset_env)
    if acf.size == 0:
        return None
    bpms = bpm_axis(sr, hop, len(acf))
    mask = (bpms >= tempo_min) & (bpms <= tempo_max)
    if not np.any(mask):
        return None
    prior = np.exp(-0.5 * ((bpms[mask] - mu) / sigma) ** 2)
    return float(bpms[mask][np.argmax(acf[mask] * prior)])


def robust_bpm_from_beats(onset_env, sr, hop, start_bpm):
    _need_librosa()
    bt_bpm, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr,
                                                  hop_length=hop, start_bpm=start_bpm)
    bt_bpm = float(np.atleast_1d(bt_bpm)[0])
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    if len(beat_times) < 2:
        return dict(bt_bpm=float("nan"), rbt_bpm=float("nan"), beat_times=beat_times)
    rbt_bpm = 60.0 / np.median(np.diff(beat_times))
    return dict(bt_bpm=bt_bpm, rbt_bpm=float(rbt_bpm), beat_times=beat_times)


def _bad(x):
    return x is None or (isinstance(x, float) and (np.isnan(x) or x <= 0))


def tactus_correction(bpm, mu):
    if _bad(bpm):
        return bpm, False
    if abs(bpm - 2 * mu) < abs(bpm - mu):
        return bpm / 2.0, True
    return bpm, False


def grid_fit_score(onset_env, bpm, sr, hop, n_phase=32):
    """Mean onset strength on a beat grid at `bpm`, for the best of n_phase phases."""
    if _bad(bpm):
        return -np.inf
    period = 60.0 * sr / (hop * bpm)
    if period < 8:
        return -np.inf
    N = len(onset_env)
    best = -np.inf
    for phi in np.linspace(0, period, num=n_phase, endpoint=False):
        idx = (phi + np.arange(0, N, period)).astype(int)
        idx = idx[idx < N]
        if idx.size >= 4:
            best = max(best, float(onset_env[idx].mean()))
    return best


def choose_octave_by_fit(onset_env, bpm, sr, hop, prefer_slower_if_close=True, close_margin=0.03):
    if _bad(bpm):
        return bpm, False, {"score_x": np.nan, "score_half": np.nan}
    sx = grid_fit_score(onset_env, bpm, sr, hop)
    sh = grid_fit_score(onset_env, bpm / 2, sr, hop)
    scores = {"score_x": sx, "score_half": sh}
    if sh > sx * (1 + close_margin):
        return bpm / 2.0, True, scores
    if prefer_slower_if_close and abs(sh - sx) <= abs(sx) * close_margin and bpm / 2.0 >= 40:
        return bpm / 2.0, True, scores
    return bpm, False, scores


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyze_file(path, preset="generic", **overrides):
    """Analyse one audio file. Returns a dict with all estimates and the beat times."""
    s = settings(preset, **overrides)
    y, sr = load_preemphasize(path, sr=s["sr"], preemph=s["preemph"])
    env = onset_envelope(y, sr, hop=s["hop"], smooth_frames=s["smooth_frames"])

    acf_bpm = acf_pick_tempo(env, sr, s["hop"], s["tmin"], s["tmax"], mu=s["mu"], sigma=s["sigma"])
    beats = robust_bpm_from_beats(env, sr, s["hop"], start_bpm=s["start_bpm"])
    rbt, acf = beats["rbt_bpm"], acf_bpm
    rbt_halved = acf_halved = False
    if s["tactus"]:
        rbt, rbt_halved = tactus_correction(rbt, s["mu"])
        acf, acf_halved = tactus_correction(acf, s["mu"])

    fit_scores = {}
    if s["octave_grid"]:
        if not _bad(rbt) and rbt > s["grid_threshold"]:
            rbt, h, fit_scores["RBT"] = choose_octave_by_fit(env, rbt, sr, s["hop"])
            rbt_halved = rbt_halved or h
        if not _bad(acf) and acf > s["grid_threshold"]:
            acf, h, fit_scores["ACF"] = choose_octave_by_fit(env, acf, sr, s["hop"])
            acf_halved = acf_halved or h

    reported = rbt if not _bad(rbt) else acf
    return {
        "Filename": os.path.basename(path),
        "Preset": preset,
        "Reported_BPM": None if _bad(reported) else round(float(reported), 1),
        "RBT_BPM_final": rbt,
        "BeatTracker_Tempo_BPM": beats["bt_bpm"],
        "ACF_BPM_final": acf,
        "Num_Beats": len(beats["beat_times"]),
        "RBT_Halved": rbt_halved,
        "ACF_Halved": acf_halved,
        "Duration_s": round(len(y) / sr, 2),
        "OctaveFitScores": fit_scores,
        "Beat_Times_sec": beats["beat_times"],
    }


def analyze_folder(folder, preset="generic", out_dir=None, save_beats=False, verbose=True, **overrides):
    """Analyse every audio file in `folder`. Writes tempo_summary_<preset>.csv and returns it."""
    s = settings(preset, **overrides)
    out_dir = out_dir or folder
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(AUDIO_EXT))
    if not files:
        raise FileNotFoundError(f"No audio files ({', '.join(AUDIO_EXT)}) in {folder}")
    rows = []
    for i, fn in enumerate(files, 1):
        try:
            res = analyze_file(os.path.join(folder, fn), preset=preset, **overrides)
            rows.append(res)
            if save_beats and len(res["Beat_Times_sec"]) > 1:
                pd.DataFrame({"Beat_Index": np.arange(1, len(res["Beat_Times_sec"]) + 1),
                              "Beat_Time_sec": res["Beat_Times_sec"]}).to_csv(
                    os.path.join(out_dir, os.path.splitext(fn)[0] + "_beats.csv"), index=False)
            if verbose:
                print(f"[{i}/{len(files)}] {fn}: {res['Reported_BPM']} BPM")
        except Exception as e:
            print(f"[{i}/{len(files)}] {fn}: FAILED ({e})")
    df = pd.DataFrame(rows).drop(columns=["Beat_Times_sec"])
    for k, v in s.items():
        df[f"setting_{k}"] = v
    out = os.path.join(out_dir, f"tempo_summary_{preset}.csv")
    df.to_csv(out, index=False)
    if verbose:
        print(f"Saved {out} ({len(df)} files). Halved by octave handling: {int(df['RBT_Halved'].sum())}")
    return df


def main(argv=None):
    p = argparse.ArgumentParser(description="Tempo (BPM) estimation for unaccompanied singing.")
    p.add_argument("folder", help="folder with audio files")
    p.add_argument("--preset", default="generic", choices=list(PRESETS))
    p.add_argument("--out", default=None, help="output folder (default: the audio folder)")
    p.add_argument("--save-beats", action="store_true", help="also write one beat-time CSV per file")
    for k in ("mu", "sigma", "tmin", "tmax", "start_bpm", "grid_threshold"):
        p.add_argument(f"--{k.replace('_', '-')}", type=float, default=None)
    for k in ("hop", "smooth_frames", "sr"):
        p.add_argument(f"--{k.replace('_', '-')}", type=int, default=None)
    p.add_argument("--preemph", type=float, default=None)
    p.add_argument("--tactus", choices=["on", "off"], default=None)
    p.add_argument("--octave-grid", choices=["on", "off"], default=None)
    a = p.parse_args(argv)
    ov = {k: getattr(a, k) for k in ("mu", "sigma", "tmin", "tmax", "start_bpm", "grid_threshold",
                                     "hop", "smooth_frames", "sr", "preemph")}
    if a.tactus:
        ov["tactus"] = a.tactus == "on"
    if a.octave_grid:
        ov["octave_grid"] = a.octave_grid == "on"
    analyze_folder(a.folder, preset=a.preset, out_dir=a.out, save_beats=a.save_beats, **ov)


if __name__ == "__main__":
    sys.exit(main())

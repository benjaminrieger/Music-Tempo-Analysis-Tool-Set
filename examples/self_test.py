#!/usr/bin/env python3
"""
Self-test: generates synthetic sung melodies at known tempi, runs vocal_tempo on
them, and checks that the estimates come out right. Run it once after installing.

    python examples/self_test.py

The test audio (vowel-like harmonic tones with soft attacks, slight timing jitter
and a little vibrato) is written to examples/test_audio/. It contains no real
recordings, so it can be shared freely.
"""

import os
import sys

import numpy as np
from scipy.io import wavfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import vocal_tempo as vt  # noqa: E402

SR = 22050
TEMPI = [60, 75, 90, 110]      # true BPM of the synthetic melodies
DURATION = 30.0                # seconds per file
SCALE = [0, 2, 4, 5, 7, 9, 7, 5, 4, 2]  # semitones above the tonic


def synth_melody(bpm, seed):
    rng = np.random.default_rng(seed)
    ioi = 60.0 / bpm
    n = int(DURATION / ioi)
    y = np.zeros(int(SR * (DURATION + 1)))
    t0 = 0.25
    f_tonic = 220.0 * 2 ** (rng.integers(-3, 4) / 12)
    for i in range(n):
        onset = t0 + i * ioi + rng.normal(0, 0.01 * ioi)      # 1% timing jitter
        dur = ioi * rng.uniform(0.75, 0.95)
        t = np.arange(int(dur * SR)) / SR
        f0 = f_tonic * 2 ** (SCALE[i % len(SCALE)] / 12)
        vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t)
        phase = 2 * np.pi * np.cumsum(f0 * vib) / SR
        tone = sum((0.6 ** h) * np.sin((h + 1) * phase) for h in range(6))
        env = np.minimum(1, t / 0.04) * np.exp(-1.2 * t) * np.minimum(1, (dur - t) / 0.05)
        start = int(onset * SR)
        seg = tone * env * (0.6 if i % 2 else 1.0)            # mild accent pattern
        y[start:start + len(seg)] += seg[: len(y) - start]
    y += rng.normal(0, 0.003, len(y))                         # room noise
    return (y / np.abs(y).max() * 0.8).astype(np.float32)


def main():
    folder = os.path.join(HERE, "test_audio")
    os.makedirs(folder, exist_ok=True)
    for k, bpm in enumerate(TEMPI):
        wavfile.write(os.path.join(folder, f"synthetic_{bpm:03d}bpm.wav"), SR, synth_melody(bpm, k))
    print(f"Wrote {len(TEMPI)} test files to {folder}\n")

    df = vt.analyze_folder(folder, preset="generic", verbose=False)
    ok_all = True
    print(f"{'file':28s} {'true':>5s} {'estimate':>9s}  result")
    for _, r in df.iterrows():
        true = float(r["Filename"].split("_")[1][:3])
        est = r["Reported_BPM"]
        if est is None or np.isnan(est):
            res, ok = "no estimate", False
        elif abs(est - true) <= 0.04 * true:
            res, ok = "PASS", True
        elif any(abs(est - m * true) <= 0.04 * m * true for m in (0.5, 2)):
            res, ok = "octave error (half or double)", False
        else:
            res, ok = "FAIL", False
        ok_all &= ok
        print(f"{r['Filename']:28s} {true:5.0f} {est:9.1f}  {res}")
    print("\nAll tests passed." if ok_all else
          "\nSome tests did not pass. Check the installation (docs/INSTALL.md) or report the output.")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())

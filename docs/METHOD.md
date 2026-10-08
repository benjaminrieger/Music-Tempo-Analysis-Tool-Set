# Method and parameters

## Pipeline

For each audio file, `vocal_tempo.py` does the following:

1. **Load and pre-emphasise.** Mono, native sample rate (or `sr`). Pre-emphasis
   (`preemph`, default 0.97) lifts high frequencies so consonant and note onsets
   stand out against sustained vowels.
2. **Onset envelope.** `librosa.onset.onset_strength` with hop `hop`
   (default 512 samples, about 11.6 ms at 44.1 kHz), normalised and smoothed with a
   moving average of `smooth_frames` frames (default 10). Smoothing suppresses
   small onsets inside a sung note.
3. **Beat-tracker tempo (RBT).** `librosa.beat.beat_track` on that envelope,
   seeded with `start_bpm`. Tempo = 60 / median inter-beat interval. The median
   makes it robust to a few misplaced beats. This is the reported value.
4. **Autocorrelation tempo (ACF).** Unbiased autocorrelation of the envelope,
   restricted to `tmin` to `tmax` BPM and weighted by a Gaussian prior centred on
   `mu` with width `sigma`. Reported only if the beat tracker fails.
5. **Octave handling (optional).**
   - `tactus`: an estimate closer to 2 x `mu` than to `mu` is halved.
   - `octave_grid`: for estimates above `grid_threshold`, the tool places a beat
     grid at BPM and at BPM/2 (best of 32 phases each) and compares the mean onset
     strength on the grid. If half tempo fits clearly better (more than 3%) or
     about equally well, half tempo is kept.

Output per file: `Reported_BPM`, the RBT, beat-tracker and ACF estimates, number
of beats, whether octave handling halved the estimate, duration, and all
settings used (columns `setting_*`), so every result can be reproduced.

## Settings

| Setting | generic | lullaby | What it does |
|---|---|---|---|
| `mu` | 80 | 60 | Expected tempo centre (BPM). Used by the ACF prior and the tactus correction |
| `sigma` | 5 | 5 | Width of the ACF prior (BPM). Small = ACF stays close to `mu` |
| `tmin`, `tmax` | 40, 150 | 40, 100 | Tempo window for the ACF |
| `start_bpm` | = `mu` | 60 | Seed for librosa's beat tracker |
| `tactus` | on | on | Halve estimates closer to 2 x `mu` than to `mu` |
| `octave_grid` | off | on | Grid-fit check of BPM vs BPM/2 above `grid_threshold` |
| `grid_threshold` | 95 | 95 | BPM above which the grid check runs |
| `hop` | 512 | 512 | Analysis hop in samples |
| `preemph` | 0.97 | 0.97 | Pre-emphasis; 0 disables |
| `smooth_frames` | 10 | 10 | Envelope smoothing |

The `generic` preset reproduces the original method with its default prior; the
`lullaby` preset reproduces the settings of the cross-continental lullaby study
(free singing, octave grid check on).

## Adapting to other music

The settings that shape results most are `mu`, `start_bpm` and `tactus`,
because together they decide which metrical level is reported:

- With `tactus` on, anything above 1.5 x `mu` is halved. For material that is
  genuinely fast (for example play songs around 120 BPM), set `mu` near the
  expected tempo or switch `tactus` off.
- `sigma = 5` makes the ACF fallback almost a lookup of `mu`. If you rely on the
  ACF, use 20 to 30.
- Set `tmax` well above the fastest tempo you expect, or fast songs get clipped.

Example, command line:

    python vocal_tempo.py my_audio --mu 110 --tmin 60 --tmax 200 --sigma 25 --tactus off

Example, Python:

    df = vt.analyze_folder("my_audio", preset="generic", mu=110, tmax=200, sigma=25, tactus=False)

Try settings on a handful of files you have checked by ear before running a
whole corpus.

## Octave check with hand taps

No prior setting resolves the metrical level for every recording. The
recommended workflow:

1. Run `vocal_tempo.py` on all files.
2. Tap every file with `tools/tempo_tapper.html` (blind, randomised order).
3. Run `tools/octave_check.py` with the summary and the tap CSV.

`octave_check.py` divides the algorithm BPM by the tapped BPM and assigns the
ratio to the nearest of 1:3, 1:2, 2:3, 1:1, 3:2, 2:1, 3:1 on a log scale:

| Nearest relation | Meaning | Action |
|---|---|---|
| 2:1 | algorithm counted double time | corrected = algorithm / 2 |
| 1:2 | algorithm counted half time | corrected = algorithm x 2 |
| 3:1, 1:3 | triple relation | flagged for manual review |
| 1:1, 3:2, 2:3 | same level, or a 3:2 relation that halving or doubling would not fix | unchanged |

In practice this means a value is corrected when the ratio is above about 1.73
or below about 0.58. The tap is used only to decide the metrical level; the
corrected tempo is still the algorithm's value (halved or doubled), because the
algorithm measures the tempo more precisely than tapping does.

In the lullaby study, 37 of 506 recordings (7%) were corrected this way.

## Limitations

- One tempo per file. Tempo changes and rubato within a recording are summarised
  by the median beat interval, not modelled.
- Free singing often has no single correct metrical level. The octave check makes
  the choice explicit and reproducible; it does not remove the ambiguity.
- Very short recordings (under about 10 seconds or fewer than 4 beats) give
  unstable estimates. Check `Num_Beats` and `Duration_s`.

# Music Tempo Analysis Tool Set

Tools for measuring the tempo (BPM) of **unaccompanied singing**: lullabies,
play songs, field recordings, a cappella. Standard beat trackers are tuned for
produced music with percussion and often fail on soft vocal onsets, tempo drift
and missing drums. This tool set adapts librosa to that material and adds a hand
tapping tool to catch the errors no algorithm settings fully avoid.

Developed for the cross-continental lullaby studies at TU Dresden (CeTI).

## What is in here

| Path | What it is |
|---|---|
| [`vocal_tempo.py`](vocal_tempo.py) | The tempo algorithm. Command line or Python import. Presets `generic` and `lullaby`; every setting adjustable |
| [`notebooks/01_quickstart.ipynb`](notebooks/01_quickstart.ipynb) | Jupyter walkthrough: analyse a folder, inspect beats on one file |
| [`notebooks/02_lullaby_study_analyzer.ipynb`](notebooks/02_lullaby_study_analyzer.ipynb) | The original notebook from the lullaby studies, for exact reproduction |
| [`tools/tempo_tapper.html`](tools/tempo_tapper.html) | Browser tool for blind hand-tapping of tempo. No installation |
| [`tools/octave_check.py`](tools/octave_check.py) | Compares algorithm tempi with hand taps and corrects double/half-time errors |
| [`tools/convert_to_pcm.py`](tools/convert_to_pcm.py) | Converts audio to plain WAV (needed when the tapper plays no sound) |
| [`paper_analysis/`](paper_analysis) | Analysis scripts of the lullaby tempo paper: octave check, statistics, figures, intra-rater check |
| [`examples/self_test.py`](examples/self_test.py) | Generates synthetic singing at known tempi and checks the installation |
| [`docs/presentation/`](docs/presentation) | Talk "Adapting Tempo Analysis for Your Data": tuning librosa for vocal and non-standard audio (PDF and editable PPTX) |
| [`docs/`](docs) | Installation, method and parameters, tapper guide |

## Quick start

    git clone https://github.com/benjaminrieger/Music-Tempo-Analysis-Tool-Set.git
    cd Music-Tempo-Analysis-Tool-Set
    python -m pip install -r requirements.txt
    python examples/self_test.py
    python vocal_tempo.py path/to/your/audio --preset generic

No git? Click **Code > Download ZIP** above. Using Anaconda? See
[docs/INSTALL.md](docs/INSTALL.md).

The result is `tempo_summary_generic.csv` in your audio folder, one row per file,
with the reported BPM, the separate estimates, and all settings used.

## Recommended workflow

1. **Analyse** all recordings with `vocal_tempo.py`. Pick or adapt a preset
   ([docs/METHOD.md](docs/METHOD.md#adapting-to-other-music)).
2. **Tap** every recording blind with `tools/tempo_tapper.html`
   ([docs/TEMPO_TAPPER.md](docs/TEMPO_TAPPER.md)).
3. **Check octaves**: `python tools/octave_check.py --summary <summary.csv> --taps <taps.csv>`.
   Files where the algorithm counted double or half time are corrected;
   triple relations are flagged for review.

The algorithm gives the precise tempo; the tap decides the metrical level.

## Limits of the algorithm

In the cross-continental lullaby study, `vocal_tempo.py` was not reliable on phone
recordings of unaccompanied singing: it placed many lullabies above 90 BPM. The paper
therefore uses tempo values from a digital audio workstation, checked for octave
errors with the tapper and `build_tempo_corrected.py`. Whatever tool produces your
tempo values, check them against blind hand taps before analysing them.

## Adapting the algorithm

Most results depend on four settings: `mu` (expected tempo), `start_bpm` (beat
tracker seed), `tactus` (halving of fast estimates) and `tmax`. For example, for
faster material:

    python vocal_tempo.py my_audio --mu 110 --tmax 200 --sigma 25 --tactus off

All settings and their effects: [docs/METHOD.md](docs/METHOD.md).

## Citation

If you use this tool set, please cite it (see [CITATION.cff](CITATION.cff), or
use "Cite this repository" on the GitHub page).

## License

MIT, see [LICENSE](LICENSE). Contributions and issue reports are welcome.

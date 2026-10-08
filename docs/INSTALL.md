# Installation

You need Python 3.9 or newer. Two routes; pick one.

## Route A: Anaconda (recommended if you use Jupyter)

1. Install Anaconda from <https://www.anaconda.com/download>.
2. Open **Anaconda Prompt** (Windows) or a terminal (macOS/Linux) and go to the
   downloaded folder:

       cd path/to/Music-Tempo-Analysis-Tool-Set

3. Create and activate the environment:

       conda env create -f environment.yml
       conda activate vocal-tempo

4. Check the installation:

       python examples/self_test.py

5. Start Jupyter and open `notebooks/01_quickstart.ipynb`:

       jupyter notebook

## Route B: plain Python with pip

    cd path/to/Music-Tempo-Analysis-Tool-Set
    python -m pip install -r requirements.txt
    python examples/self_test.py

Use `python -m pip`, not `pip`. On computers with several Python installations,
`python -m pip` installs into the same Python that `python` runs, which avoids
"No module named ..." errors.

## Download without git

On the GitHub page, click **Code > Download ZIP** and unzip it. With git:

    git clone https://github.com/benjaminrieger/Music-Tempo-Analysis-Tool-Set.git

## Troubleshooting

| Problem | Fix |
|---|---|
| `can't open file ... vocal_tempo.py` | The terminal is in a different folder. `cd` into the repository folder first |
| `No module named librosa` | Environment not active (`conda activate vocal-tempo`) or packages installed into another Python (use `python -m pip`) |
| `No audio files found` | Check the folder path; supported: .wav .mp3 .flac .m4a .ogg |
| `PermissionError` when saving a CSV | The file is open in Excel. Close it and run again |
| Tapper plays no sound (player at 0:00) | Audio is MP3 inside a .wav name. Run `python tools/convert_to_pcm.py in_folder out_folder` |
| Windows PowerShell: `%USERPROFILE%` not found | Use `$HOME` in PowerShell, e.g. `cd $HOME\Downloads` |
| Slow on long files | Add `--sr 22050` (resamples; usually fine for tempo) |

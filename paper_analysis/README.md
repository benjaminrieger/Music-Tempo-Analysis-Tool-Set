# Analysis scripts: cross-continental lullaby tempo paper

These scripts produce every number, table and figure in the paper
"Lullabies Are Sung Slower Than Love Songs and Sleep Songs Across Five Continents".
The recordings and the participant data are not part of this repository.

| Script | Step |
|---|---|
| `build_tempo_corrected.py` | Octave check. Combines the tempo values (DAW estimates, sheet "Experimental Data") with the blind hand taps from `tools/tempo_tapper.html`, halves or doubles values whose ratio to the tap is nearest 2:1 or 1:2, and writes `Tempo_Corrected.xlsx` |
| `tempo_analysis.py` | All statistics and figures: linear mixed models on log2 BPM, random-slopes check, continent tests, paired within-participant comparisons, exploratory covariates, sensitivity analyses. Writes `results.xlsx`, `report.txt` and `figures/` |
| `retap_prepare.py` | Inter-rater check, step 1: draws 50 random included recordings (fixed seed) and copies them into a new folder for a second rater, who taps them blind |
| `retap_compare.py` | Inter-rater check, step 2: compares the second rater with the first (same metrical level, same octave decision, ICC(A,1) on log2 BPM) |

## Folder layout

The scripts find their files relative to the project folder, so place them in
`02_code` of a project laid out like this:

    project/
      01_data/     source workbook, tapper CSV export(s)
      02_code/     these scripts
      03_output/   Tempo_Corrected.xlsx and tempo_analysis_output/ are written here

## Run

    python -m pip install pandas numpy scipy matplotlib openpyxl statsmodels
    python build_tempo_corrected.py
    python tempo_analysis.py

`statsmodels` is optional: the mixed models are fitted with a built-in REML/ML engine,
and statsmodels MixedLM is used only as a cross-check when it is installed.

## Settings that change results

All at the top of each script: `PRIMARY` and `MANUAL_DECISIONS` (octave check),
`EXCLUDE_COUNTRIES` (default Australia, which belongs to none of the five sampled
continents), `TRAINING_BLANK_AS`, `MERGE_OLDEST_AGE` and `USE_LOG` (analysis).

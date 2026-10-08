# Tempo Tapper

`tools/tempo_tapper.html` is a browser tool for annotating the beat tempo of
recordings by hand. It runs locally: nothing is uploaded, no installation is
needed, and it works offline.

## Two ways to use it

**As an octave check for the algorithm.** This is how it was used in the lullaby
study. The algorithm gives the precise tempo; the hand tap gives the metrical
level (which pulse is felt as the beat). `tools/octave_check.py` then finds files
where the algorithm counted double or half time and corrects them. See
[METHOD.md](METHOD.md#octave-check-with-hand-taps).

**As the primary measurement.** For corpora where the algorithm is unreliable,
the taps themselves can serve as the tempo measure. The reliability features
below exist for this use.

## Start

1. Make sure your audio plays in the browser. If the player stays at 0:00, the
   files are probably MP3 data inside a `.wav` name. Run
   `python tools/convert_to_pcm.py your_audio your_audio_pcm` and use the new folder.
2. Open `tempo_tapper.html` by double-clicking it (Chrome or Edge recommended).
3. Enter your initials and click **Choose recordings folder**.
4. Per clip: press **Space** to start playback, tap the beat with **Space** for
   several seconds, press **Enter** to save and go to the next clip.

| Key | Action |
|---|---|
| Space | First press starts playback, then each press is a tap |
| Enter | Save and go to the next clip |
| R | Clear the taps and replay |
| P | Replay |
| Skip button | Mark a clip as unusable (too short, unclear, noise) |

## Stopping and resuming

Progress is saved in the browser after every clip. Reopen the file, choose the
same folder, and the tool continues at the first clip without a tap.
Browser storage can be cleared, so click **Export CSV** before you stop. In a
new session or on another computer, click **Resume from CSV** and load that
file before choosing the folder.

## Design choices

| Choice | Reason |
|---|---|
| Blind presentation: only "Clip 47 of 520" is shown | The annotator cannot tap to an expectation based on filename, condition or algorithm output |
| Tempo = 60000 / median inter-tap interval | One missed or extra tap does not move the result |
| Stability (SD of intervals) is shown but never used to adjust the value | The annotator decides whether to redo; the software does not edit numbers |
| Random order from a seed based on folder name and file count | Reduces order effects; a second rater on the same folder sees the same order |
| About 20% of clips flagged for a second pass | Re-tapping them (pass toggle) gives intra-rater reliability |
| No access to algorithm output | Keeps the taps independent of what they are meant to check |

## Output CSV

| Column | Meaning |
|---|---|
| filename | Audio file name (join key with the algorithm summary) |
| tapped_bpm | 60000 / median inter-tap interval |
| n_taps, n_ibis | Number of taps and intervals |
| median_ibi_ms, sd_ibi_ms | Median and SD of the intervals |
| pass | 1 = first pass, 2 = reliability re-tap |
| rater | Initials |
| skipped | 1 if marked unusable |
| session_started, tapped_iso | Timestamps |

## Limitations

Free singing often has no single correct metrical level; two careful listeners
can tap an octave apart. Tapping at a perceived level and evaluating with
octave tolerance handles this, it does not remove it. Taps of loosely timed
singing are also noisy (a spread of 15 to 20% of the interval is common), so a
tap is a good guide to the metrical level but not a precise tempo.

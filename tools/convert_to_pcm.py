#!/usr/bin/env python3
"""
convert_to_pcm.py: re-encode audio to plain 16-bit PCM WAV.

Why: some recording platforms (for example Jotform's voice recorder) store MP3
data inside files named .wav. librosa reads these, but web browsers do not, so
tools/tempo_tapper.html stays silent. Converting to PCM fixes that. Sample rate,
channels and duration are kept; file names stay identical (extension .wav).

    python tools/convert_to_pcm.py path/to/audio path/to/audio_pcm

Originals are not modified. Already converted files are skipped, so the script
can be re-run.
"""

import os
import sys

import soundfile as sf

EXT = (".wav", ".mp3", ".flac", ".ogg", ".m4a")


def main(src, dst):
    if not os.path.isdir(src):
        sys.exit(f"Source folder not found: {src}")
    os.makedirs(dst, exist_ok=True)
    files = sorted(f for f in os.listdir(src) if f.lower().endswith(EXT))
    done = skipped = 0
    failed = []
    for f in files:
        out = os.path.join(dst, os.path.splitext(f)[0] + ".wav")
        if os.path.exists(out):
            skipped += 1
            continue
        try:
            data, sr = sf.read(os.path.join(src, f))
            sf.write(out, data, sr, subtype="PCM_16")
            done += 1
        except Exception as e:
            failed.append((f, str(e)))
    print(f"Converted {done}, already present {skipped}, failed {len(failed)} -> {dst}")
    for f, e in failed:
        print(f"  {f}: {e}")
    if failed:
        print("For files soundfile cannot read, use ffmpeg: ffmpeg -i in.wav -c:a pcm_s16le out.wav")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

# Pianotrans Run Tools

One-line summary: Pianotrans launchers with integrated BPM fixing, MIDI cleanup, hand-channel marking, and review export. The main launcher uses CUDA / CPU, while an Apple GPU / MPS-capable launcher is kept for testing and comparison.

[Chinese README](README.md)

This folder contains Pianotrans transcription entrypoints and the post-processing tools added around their MIDI output: BPM fixing, MIDI statistics, conservative rule-based MIDI cleanup, provisional hand-splitting by MIDI channel, and compact MIDI review export. All `.command` files are intended to be double-clickable on macOS. The main entrypoint uses CUDA / CPU; a separate Apple GPU / MPS-capable entrypoint is kept for testing and comparison.

## Main Pipeline

### `pianotrans.command`

Main transcription entrypoint. Double-click it, then choose one or more audio files. MIDI files are written next to the selected audio files.

Device selection order:

```text
CUDA -> CPU
```

Pipeline:

```text
Pianotrans inference
-> write original MIDI
-> write MIDI stats
-> detect BPM from source audio
-> write BPM-fixed MIDI
-> rule-based conservative cleanup
-> provisional hand split by MIDI channel
```

Output files:

```text
song.mid
song_stats.txt
song_bpmfix.mid
song_bpmfix_cleaned.mid
```

`song_stats.txt` contains the original MIDI quality stats, BPMFix stats, cleanup stats, and hand-split stats.

If `song.mid` already exists, the pipeline does not run transcription again. It only fills in missing stats, BPM-fixed MIDI, and cleaned MIDI.

### `pianotrans_mps.command`

Preserved Apple GPU / MPS-capable entrypoint. It runs the same pipeline as `pianotrans.command`, but uses this device selection order:

```text
MPS -> CUDA -> CPU
```

On the tested M2 MacBook Air, this Pianotrans model was slower on MPS than on CPU, so `pianotrans.command` is the recommended daily entrypoint.

## Standalone Tools

### `bpmfix.command`

Runs BPM detection and MIDI BPM fixing only.

Usage:

1. If you already know the BPM, enter it in the terminal.
2. If you do not know the BPM, press Return, then choose the source audio file for Essentia BPM detection.
3. Choose the MIDI file to fix.
4. The tool writes `*_bpmfix.mid`.

Automatic BPM detection records the raw detected BPM and applies a rounded integer BPM. Manual BPM input is used as entered.

The fix keeps the real playback speed and rewrites MIDI ticks plus tempo metadata:

```text
new_ticks = old_ticks * detected_bpm / 120
```

### `midi_stats.command`

Runs MIDI quality statistics only.

Usage:

1. Choose a MIDI file.
2. The tool writes `*_stats.txt`.

Statistics:

```text
Total notes
Very short notes (< 0.050s)
Low velocity notes (<= 30)
Lowest note
Highest note
Pitch span
Average velocity
Max polyphony
```

Pitch values include both MIDI note number and English pitch name, for example `24 (C1)`.

### `clean_midi_rules.command`

Runs first-stage conservative rule-based cleanup only.

Usage:

1. Choose a MIDI file.
2. The tool writes `*_cleaned.mid`.
3. The tool writes `*_clean_report.txt`.

When run standalone, `clean_midi_rules.command` writes `*_clean_report.txt`. In the full `pianotrans.command` pipeline, the cleanup report is appended to the original `song_stats.txt`.

The cleanup step removes only highly likely artifacts. It does not perform musical semantic judgment, hand splitting, quantization, chord analysis, key analysis, or melody analysis.

Current rules:

```text
duration < 0.03s
velocity < 20
velocity < 35 and duration < 0.08s
pitch outside 21-108
```

Cleanup report example:

```text
MIDI rule cleaning stats
Input: song_bpmfix.mid
Output: song_bpmfix_cleaned.mid
Original notes: 1000
Removed notes: 35 (3.50%)
Kept notes: 965 (96.50%)
Rule removals:
- Duration < 0.030s: 12 (1.20%)
- Velocity < 20: 3 (0.30%)
- Velocity < 35 and duration < 0.080s: 18 (1.80%)
- Pitch outside 21-108: 2 (0.20%)
```

All percentages use `Original notes` as the denominator.

### `hand_split_channels.command`

Marks provisional left/right hand assignment directly on a cleaned MIDI file by changing note channels only.

It does not create separate instrument tracks and does not remove notes.

Channel mapping:

```text
MIDI channel 1 = right hand
MIDI channel 3 = left hand
```

For libraries such as `mido`, this means:

```text
channel 0 = MIDI channel 1
channel 2 = MIDI channel 3
```

This step is intended to make the MIDI easier to inspect and edit in Logic Pro score view.

### `generate_midi_review.py`

Reads a processed MIDI and writes a compact English Markdown score facts table. It does not modify the MIDI.

Command:

```bash
python generate_midi_review.py input.mid
```

Default output:

```text
midi_review.md
```

Current output structure:

```text
Global Info
Notes
```

Detailed spec:

```text
MIDI_REVIEW_SPEC.md
```

## Python Entrypoints

Python scripts used by the `.command` launchers:

```text
pianotrans.py
pianotrans_mps.py
bpmfix.py
midi_stats_command.py
clean_midi_rules.py
hand_split_channels.py
generate_midi_review.py
```

Shared helpers:

```text
bpmfix_utils.py
midi_stats.py
```

## Dependencies

Pianotrans Python environment:

```text
./.venv
```

Essentia BPM detection environment:

```text
$HOME/.local/share/pianotrans-bpm-env
```

Global ffmpeg:

```text
$HOME/.local/bin/ffmpeg
```

Default model checkpoint path:

```text
$HOME/piano_transcription_inference_data/note_F1=0.9677_pedal_F1=0.9186.pth
```

Overridable environment variables:

```text
PIANOTRANS_BPM_ENV
PIANOTRANS_BPM_PYTHON
```

## Notes

- `pianotrans.py` tries CUDA, then CPU.
- `pianotrans_mps.py` tries MPS, then CUDA, then CPU; on Apple Silicon with PyTorch MPS available, it uses Apple GPU.
- BPM fixing assumes a fixed BPM and does not build a tempo map.
- Rule cleanup is conservative preprocessing. More complex decisions should be handled by later feature extraction or ML/classifier workflows.

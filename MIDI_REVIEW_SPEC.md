# MIDI Review Data Spec

This document describes a planned Python tool for exporting a processed Pianotrans MIDI file into an English Markdown "score facts table".

The tool is intended for later use with large language models or human review. It must only read MIDI and write Markdown. It must not modify MIDI.

## Tool

```bash
python generate_midi_review.py input.mid
```

Default output:

```text
<input_stem>_midi_review.md
```

## Scope

Input should be a fully processed Pianotrans MIDI, typically:

```text
*_bpmfix_cleaned.mid
```

Expected preprocessing before this tool:

```text
Pianotrans inference
-> BPM fix
-> conservative rule cleaning
-> provisional hand split by MIDI channel
```

This tool only extracts facts from the MIDI.

## Assumptions

First runnable version should assume:

- Single stable tempo is the common case.
- Single stable time signature is the common case.
- MIDI channel 1 means right hand.
- MIDI channel 3 means left hand.
- mido uses 0-based channels:
  - channel `0` = MIDI channel 1 = right hand
  - channel `2` = MIDI channel 3 = left hand

If unexpected channels are found, notes must not disappear. Use pitch fallback:

```text
pitch < 60  -> Left
pitch >= 60 -> Right
```

If multiple tempo or time signature events are found, still generate the Markdown using the active event at each note start.

## Thresholds

All thresholds should be constants near the top of the file.

Recommended first-version thresholds:

```text
CHORD_GROUP_WINDOW_SECONDS = 0.05
NEARBY_INTERVAL_WINDOW_SECONDS = 0.12

VERY_SHORT_SECONDS = 0.03
SHORT_SECONDS = 0.08
VERY_WEAK_VELOCITY = 20
WEAK_VELOCITY = 35

LOW_REGISTER_MAX_PITCH = 40
HIGH_REGISTER_MIN_PITCH = 88
DENSE_GROUP_NOTE_COUNT = 6
END_OVERLAP_SECONDS = 0.03
SAME_PITCH_OVERLAP_SECONDS = 0.0
```

These values are intentionally conservative and can be tuned later.

## Output Structure

```markdown
# MIDI Review Data

## Global Info

...

## Notes
...
```

## Global Info

Include:

- source filename
- BPM
- time signature
- total bars
- total notes
- left note count
- right note count

Example:

```text
- Source filename: song_bpmfix_cleaned.mid
- BPM: 106.00
- Time signature: 4/4
- Total bars: 89
- Total notes: 3219
- Left note count: 960
- Right note count: 2259
```

## Flags

Use only these fixed flags:

```text
normal
very_short
short
very_weak
weak
high_register
low_register
dense
same_pitch_overlap
end_overlap
```

Do not mark `isolated` notes in the first compact version. That flag creates too much noise for a score-like review file.

Do not include higher-level musical judgment flags in the first version.

Excluded for now:

```text
octave_outlier
melodic_break
large_hand_span
possible_pedal_tail
```

## Notes Table

Whole-song note facts table:

```markdown
| ID | Position | Hand | Pitch | MidiPitch | Velocity | Duration_ms | Duration_beats | ChordGroup | NearbyMaxInterval | Flags |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
```

Column definitions:

- `ID`: numeric, unique across the whole song, sorted by start time starting from `1`.
- `Position`: `Bar X Beat Y.Y`.
- `Hand`: `Left` or `Right`.
- `Pitch`: English pitch name, e.g. `C4`, `D#5`, `Bb3`.
- `MidiPitch`: original MIDI pitch number.
- `Velocity`: MIDI velocity.
- `Duration_ms`: integer milliseconds.
- `Duration_beats`: duration in beats at the current tempo, 2 decimals.
- `ChordGroup`: global chord group ID.
- `NearbyMaxInterval`: same-hand maximum pitch distance in semitones within the nearby time window. `-1` if no same-hand nearby note exists.
- `Flags`: comma-separated fixed flags. If no suspicious flags exist, write `normal`.

## Position

Compute musical position from MIDI ticks, not from seconds.

For the first version, assume the active time signature at the note start.

Example:

```text
Bar 18 Beat 3.5
```

## ChordGroup

Sort notes by start time.

Notes whose start times are within:

```text
CHORD_GROUP_WINDOW_SECONDS = 0.05
```

belong to the same chord group.

Chord group IDs are global, numeric, and start from `1`.

## NearbyMaxInterval

Definition:

```text
For a note, find all notes in the same hand whose start time differs by <= NEARBY_INTERVAL_WINDOW_SECONDS.
NearbyMaxInterval is the maximum absolute pitch distance in semitones between the current note and those nearby same-hand notes.
If no nearby same-hand note exists, use -1.
```

Recommended first-version window:

```text
NEARBY_INTERVAL_WINDOW_SECONDS = 0.12
```

Purpose:

- Detect short-time same-hand extreme jumps as factual data.
- Do not add musical judgment flags such as `melodic_break`.

## Implementation Notes

- Use Python.
- `mido` is sufficient for the first version.
- `pretty_midi` is optional, but not required.
- Output format must be stable.
- Markdown tables should be deterministic.
- The first version should favor clarity and correctness over clever musical interpretation.
- Do not modify MIDI.

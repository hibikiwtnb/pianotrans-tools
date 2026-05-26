# MIDI Review Data Spec

This document describes a planned Python tool for exporting a processed Pianotrans MIDI file into an English Markdown "score facts table".

The tool is intended for later use with large language models or human review. It must only read MIDI and write Markdown. It must not modify MIDI.

## Tool

```bash
python generate_midi_review.py input.mid
```

Default output:

```text
midi_review.md
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

If multiple tempo or time signature events are found, still generate the Markdown, but record the event counts in `Global Info`.

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
NEARBY_MAX_INTERVAL_CANDIDATE = 24
END_OVERLAP_SECONDS = 0.03
SAME_PITCH_OVERLAP_SECONDS = 0.0
```

These values are intentionally conservative and can be tuned later.

## Output Structure

```markdown
# MIDI Review Data

## Global Info

...

## Flag Vocabulary

...

## Bar Summaries

...

## Notes

...

## Candidate Notes

...
```

## Global Info

Include:

- source filename
- BPM
- time signature
- ticks per beat
- tempo event count
- time signature event count
- total bars
- total notes
- left note count
- right note count
- suspicious note count
- channel mapping

Example:

```text
- Source filename: song_bpmfix_cleaned.mid
- BPM: 106.00
- Time signature: 4/4
- Ticks per beat: 384
- Tempo event count: 1
- Time signature event count: 1
- Total bars: 89
- Total notes: 3219
- Left note count: 960
- Right note count: 2259
- Suspicious note count: 184
- Channel mapping: MIDI channel 1 = Right, MIDI channel 3 = Left
```

## Flag Vocabulary

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
isolated
same_pitch_overlap
end_overlap
```

Do not include higher-level musical judgment flags in the first version.

Excluded for now:

```text
octave_outlier
melodic_break
large_hand_span
possible_pedal_tail
```

## Bar Summaries

One row per bar:

```markdown
| Bar | LeftRange | LeftNotes | RightRange | RightNotes | SuspiciousNotes |
| --- | --- | ---: | --- | ---: | ---: |
| 1 | C2-G3 | 12 | C4-E6 | 28 | 3 |
```

Definitions:

- `LeftRange`: min-max pitch name for notes assigned to Left in the bar, or `-`.
- `RightRange`: min-max pitch name for notes assigned to Right in the bar, or `-`.
- `SuspiciousNotes`: note count in the bar where flags are not `normal`.

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
- Candidate selection may use `NearbyMaxInterval >= 24`.

## Candidate Notes

List all notes that may deserve human or model attention.

Candidate conditions:

- `Flags != normal`
- or `velocity` is very low / weak
- or `duration` is very short / short
- or `NearbyMaxInterval >= NEARBY_MAX_INTERVAL_CANDIDATE`

Each candidate should include:

- ID
- Position
- Hand
- Pitch
- Velocity
- Duration_ms
- Duration_beats
- ChordGroup
- NearbyMaxInterval
- Flags
- Facts

Candidate Markdown shape:

```markdown
### Note 128

- Position: Bar 18 Beat 3.5
- Hand: Right
- Pitch: F7
- Velocity: 18
- Duration_ms: 42
- Duration_beats: 0.07
- ChordGroup: 93
- NearbyMaxInterval: 27
- Flags: weak,short
- Facts: Short weak right-hand note; nearby same-hand maximum interval is 27 semitones.
```

Facts must be short English factual descriptions. Avoid judgmental language such as "wrong", "bad", or "should be removed".

## Implementation Notes

- Use Python.
- `mido` is sufficient for the first version.
- `pretty_midi` is optional, but not required.
- Output format must be stable.
- Markdown tables should be deterministic.
- The first version should favor clarity and correctness over clever musical interpretation.
- Do not modify MIDI.

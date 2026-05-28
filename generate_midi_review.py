import argparse
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import mido


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

RIGHT_HAND_CHANNEL = 0
LEFT_HAND_CHANNEL = 2
DEFAULT_TEMPO = 500000
DEFAULT_TIME_SIGNATURE = (4, 4)

NOTE_NAMES_SHARP = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')


def pitch_name(note_number):
    octave = note_number // 12 - 1
    return '{}{}'.format(NOTE_NAMES_SHARP[note_number % 12], octave)


def hand_for_channel(channel, pitch):
    if channel == RIGHT_HAND_CHANNEL:
        return 'Right'
    if channel == LEFT_HAND_CHANNEL:
        return 'Left'
    if pitch < 60:
        return 'Left'
    return 'Right'


def collect_tempo_changes(midi_file):
    events = []
    for track in midi_file.tracks:
        absolute_ticks = 0
        for message in track:
            absolute_ticks += message.time
            if message.type == 'set_tempo':
                events.append((absolute_ticks, message.tempo))

    events.sort(key=lambda item: item[0])
    changes = [(0, DEFAULT_TEMPO)]
    for ticks, tempo in events:
        if ticks == 0:
            changes[-1] = (0, tempo)
        else:
            changes.append((ticks, tempo))
    return changes, events


def collect_time_signatures(midi_file):
    events = []
    for track in midi_file.tracks:
        absolute_ticks = 0
        for message in track:
            absolute_ticks += message.time
            if message.type == 'time_signature':
                events.append((absolute_ticks, message.numerator, message.denominator))

    events.sort(key=lambda item: item[0])
    if not events:
        events.append((0, DEFAULT_TIME_SIGNATURE[0], DEFAULT_TIME_SIGNATURE[1]))
    return events


def tick_to_second(ticks, ticks_per_beat, tempo_changes):
    seconds = 0.0
    previous_ticks, previous_tempo = tempo_changes[0]
    for change_ticks, tempo in tempo_changes[1:]:
        if ticks <= change_ticks:
            break
        seconds += mido.tick2second(change_ticks - previous_ticks, ticks_per_beat, previous_tempo)
        previous_ticks = change_ticks
        previous_tempo = tempo
    seconds += mido.tick2second(ticks - previous_ticks, ticks_per_beat, previous_tempo)
    return seconds


def tempo_at_tick(ticks, tempo_changes):
    current_tempo = tempo_changes[0][1]
    for change_ticks, tempo in tempo_changes[1:]:
        if ticks < change_ticks:
            break
        current_tempo = tempo
    return current_tempo


def time_signature_at_tick(ticks, time_signatures):
    current = time_signatures[0]
    for event in time_signatures[1:]:
        if ticks < event[0]:
            break
        current = event
    return current[1], current[2]


def beat_length_ticks(ticks_per_beat, denominator):
    return ticks_per_beat * 4 / denominator


def bar_length_ticks(ticks_per_beat, numerator, denominator):
    return beat_length_ticks(ticks_per_beat, denominator) * numerator


def position_text(ticks, ticks_per_beat, time_signatures):
    numerator, denominator = time_signature_at_tick(ticks, time_signatures)
    bar_ticks = bar_length_ticks(ticks_per_beat, numerator, denominator)
    beat_ticks = beat_length_ticks(ticks_per_beat, denominator)
    bar_index = int(ticks // bar_ticks) + 1
    ticks_in_bar = ticks - int((bar_index - 1) * bar_ticks)
    beat = ticks_in_bar / beat_ticks + 1
    return 'Bar {} Beat {:.1f}'.format(bar_index, beat)


def collect_notes(midi_file, tempo_changes):
    notes = []
    active_notes = defaultdict(list)

    for track_index, track in enumerate(midi_file.tracks):
        absolute_ticks = 0
        for message_index, message in enumerate(track):
            absolute_ticks += message.time

            if message.type == 'note_on' and message.velocity > 0:
                key = (track_index, message.channel, message.note)
                active_notes[key].append({
                    'track_index': track_index,
                    'message_index': message_index,
                    'start_ticks': absolute_ticks,
                    'start_seconds': tick_to_second(absolute_ticks, midi_file.ticks_per_beat, tempo_changes),
                    'channel': message.channel,
                    'pitch': message.note,
                    'velocity': message.velocity,
                })
            elif message.type in ('note_off', 'note_on'):
                key = (track_index, message.channel, message.note)
                if active_notes[key]:
                    start = active_notes[key].pop()
                    end_seconds = tick_to_second(absolute_ticks, midi_file.ticks_per_beat, tempo_changes)
                    notes.append({
                        'track_index': track_index,
                        'start_index': start['message_index'],
                        'end_index': message_index,
                        'start_ticks': start['start_ticks'],
                        'end_ticks': absolute_ticks,
                        'start_seconds': start['start_seconds'],
                        'end_seconds': end_seconds,
                        'channel': start['channel'],
                        'hand': hand_for_channel(start['channel'], start['pitch']),
                        'pitch': start['pitch'],
                        'velocity': start['velocity'],
                        'duration_seconds': max(0.0, end_seconds - start['start_seconds']),
                        'duration_ticks': max(0, absolute_ticks - start['start_ticks']),
                    })

    notes.sort(key=lambda note: (note['start_ticks'], note['pitch'], note['end_ticks']))
    for index, note in enumerate(notes, start=1):
        note['id'] = index
    return notes


def assign_chord_groups(notes):
    group_id = 0
    current_group_start = None

    for note in notes:
        if current_group_start is None or note['start_seconds'] - current_group_start > CHORD_GROUP_WINDOW_SECONDS:
            group_id += 1
            current_group_start = note['start_seconds']
        note['chord_group'] = group_id


def assign_nearby_max_intervals(notes):
    notes_by_hand = defaultdict(list)
    for note in notes:
        notes_by_hand[note['hand']].append(note)

    for hand_notes in notes_by_hand.values():
        for note in hand_notes:
            max_interval = -1
            for other in hand_notes:
                if other is note:
                    continue
                if abs(other['start_seconds'] - note['start_seconds']) <= NEARBY_INTERVAL_WINDOW_SECONDS:
                    max_interval = max(max_interval, abs(other['pitch'] - note['pitch']))
            note['nearby_max_interval'] = max_interval

    for note in notes:
        if 'nearby_max_interval' not in note:
            note['nearby_max_interval'] = -1


def mark_overlaps(notes):
    for note in notes:
        note['same_pitch_overlap'] = False
        note['end_overlap'] = False

    notes_by_hand_pitch = defaultdict(list)
    notes_by_hand = defaultdict(list)
    for note in notes:
        notes_by_hand_pitch[(note['hand'], note['pitch'])].append(note)
        notes_by_hand[note['hand']].append(note)

    for pitch_notes in notes_by_hand_pitch.values():
        pitch_notes.sort(key=lambda note: (note['start_seconds'], note['end_seconds']))
        for previous, current in zip(pitch_notes, pitch_notes[1:]):
            if current['start_seconds'] < previous['end_seconds'] - SAME_PITCH_OVERLAP_SECONDS:
                previous['same_pitch_overlap'] = True
                current['same_pitch_overlap'] = True

    for hand_notes in notes_by_hand.values():
        hand_notes.sort(key=lambda note: (note['start_seconds'], note['end_seconds']))
        for previous, current in zip(hand_notes, hand_notes[1:]):
            if current['start_seconds'] < previous['end_seconds'] and previous['end_seconds'] - current['start_seconds'] <= END_OVERLAP_SECONDS:
                previous['end_overlap'] = True
                current['end_overlap'] = True


def flags_for_note(note, group_sizes):
    flags = []
    if note['duration_seconds'] < VERY_SHORT_SECONDS:
        flags.append('very_short')
    elif note['duration_seconds'] < SHORT_SECONDS:
        flags.append('short')

    if note['velocity'] < VERY_WEAK_VELOCITY:
        flags.append('very_weak')
    elif note['velocity'] < WEAK_VELOCITY:
        flags.append('weak')

    if note['pitch'] >= HIGH_REGISTER_MIN_PITCH:
        flags.append('high_register')
    if note['pitch'] <= LOW_REGISTER_MAX_PITCH:
        flags.append('low_register')
    if group_sizes[note['chord_group']] >= DENSE_GROUP_NOTE_COUNT:
        flags.append('dense')
    if note['same_pitch_overlap']:
        flags.append('same_pitch_overlap')
    if note['end_overlap']:
        flags.append('end_overlap')

    return flags or ['normal']


def assign_flags(notes):
    group_sizes = defaultdict(int)
    for note in notes:
        group_sizes[note['chord_group']] += 1
    for note in notes:
        note['flags'] = flags_for_note(note, group_sizes)


def duration_beats(note, ticks_per_beat):
    return note['duration_ticks'] / ticks_per_beat


def duration_ms(note):
    return int(round(note['duration_seconds'] * 1000))


def primary_bpm(tempo_changes, note_start_ticks, note_end_ticks):
    durations_by_tempo = defaultdict(int)

    for index, (change_start_ticks, tempo) in enumerate(tempo_changes):
        if index + 1 < len(tempo_changes):
            stop_ticks = tempo_changes[index + 1][0]
        else:
            stop_ticks = note_end_ticks
        segment_start = max(change_start_ticks, note_start_ticks)
        segment_stop = min(stop_ticks, note_end_ticks)
        durations_by_tempo[tempo] += max(0, segment_stop - segment_start)

    if not durations_by_tempo:
        return mido.tempo2bpm(tempo_changes[0][1])

    primary_tempo = max(durations_by_tempo.items(), key=lambda item: item[1])[0]
    return mido.tempo2bpm(primary_tempo)


def total_bars(notes, ticks_per_beat, time_signatures):
    if not notes:
        return 0
    max_tick = max(note['end_ticks'] for note in notes)
    numerator, denominator = time_signature_at_tick(max_tick, time_signatures)
    length = bar_length_ticks(ticks_per_beat, numerator, denominator)
    return int(math.ceil(max_tick / length))


def end_ticks(notes):
    if not notes:
        return 0
    return max(note['end_ticks'] for note in notes)


def start_ticks(notes):
    if not notes:
        return 0
    return min(note['start_ticks'] for note in notes)


def format_flags(flags):
    return ','.join(flags)


def build_review(midi_path):
    midi_file = mido.MidiFile(midi_path)
    tempo_changes, _tempo_events = collect_tempo_changes(midi_file)
    time_signatures = collect_time_signatures(midi_file)
    notes = collect_notes(midi_file, tempo_changes)
    assign_chord_groups(notes)
    assign_nearby_max_intervals(notes)
    mark_overlaps(notes)
    assign_flags(notes)

    left_notes = [note for note in notes if note['hand'] == 'Left']
    right_notes = [note for note in notes if note['hand'] == 'Right']
    numerator, denominator = time_signature_at_tick(0, time_signatures)

    lines = ['# MIDI Review Data', '']
    lines.extend([
        '## Global Info',
        '',
        '- Source filename: {}'.format(os.path.basename(midi_path)),
        '- BPM: {:.2f}'.format(primary_bpm(tempo_changes, start_ticks(notes), end_ticks(notes))),
        '- Time signature: {}/{}'.format(numerator, denominator),
        '- Total bars: {}'.format(total_bars(notes, midi_file.ticks_per_beat, time_signatures)),
        '- Total notes: {}'.format(len(notes)),
        '- Left note count: {}'.format(len(left_notes)),
        '- Right note count: {}'.format(len(right_notes)),
        '',
    ])

    lines.extend([
        '## Notes',
        '',
        '| ID | Position | Hand | Pitch | MidiPitch | Velocity | Duration_ms | Duration_beats | ChordGroup | NearbyMaxInterval | Flags |',
        '| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |',
    ])
    for note in notes:
        lines.append('| {} | {} | {} | {} | {} | {} | {} | {:.2f} | {} | {} | {} |'.format(
            note['id'],
            position_text(note['start_ticks'], midi_file.ticks_per_beat, time_signatures),
            note['hand'],
            pitch_name(note['pitch']),
            note['pitch'],
            note['velocity'],
            duration_ms(note),
            duration_beats(note, midi_file.ticks_per_beat),
            note['chord_group'],
            note['nearby_max_interval'],
            format_flags(note['flags']),
        ))
    lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def default_output_path(input_midi):
    midi_path = Path(input_midi)
    return str(midi_path.with_name('{}_midi_review.md'.format(midi_path.stem)))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate MIDI review Markdown data.')
    parser.add_argument('input_midi', help='Input MIDI file.')
    parser.add_argument('-o', '--output', help='Output Markdown path.')
    args = parser.parse_args(argv)

    review = build_review(args.input_midi)
    output_path = args.output or default_output_path(args.input_midi)
    with open(output_path, 'w', encoding='utf-8') as file:
        file.write(review)
    print('Writing MIDI review: {}'.format(output_path))
    return 0


if __name__ == '__main__':
    sys.exit(main())

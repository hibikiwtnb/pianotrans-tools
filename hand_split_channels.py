import argparse
import os
import sys
import tkinter as tk
from collections import defaultdict
from tkinter import filedialog, messagebox

import mido


GROUP_START_WINDOW_SECONDS = 0.05
LEFT_STRONG_PITCH = 52
RIGHT_STRONG_PITCH = 67
MIDDLE_SPLIT_PITCH = 60
HAND_CONTINUITY_MARGIN = 5
MAX_HAND_SPAN = 16

RIGHT_HAND_CHANNEL = 0
LEFT_HAND_CHANNEL = 2

RULE_ORDER = [
    'strong_left',
    'strong_right',
    'group_relative_left',
    'group_relative_right',
    'continuity_left',
    'continuity_right',
    'middle_split_left',
    'middle_split_right',
]

RULE_LABELS = {
    'strong_left': 'pitch <= {}'.format(LEFT_STRONG_PITCH),
    'strong_right': 'pitch >= {}'.format(RIGHT_STRONG_PITCH),
    'group_relative_left': 'group relative lower note',
    'group_relative_right': 'group relative higher note',
    'continuity_left': 'closer to previous left hand pitch',
    'continuity_right': 'closer to previous right hand pitch',
    'middle_split_left': 'fallback pitch < {}'.format(MIDDLE_SPLIT_PITCH),
    'middle_split_right': 'fallback pitch >= {}'.format(MIDDLE_SPLIT_PITCH),
}


def collect_tempo_changes(midi_file):
    events = []

    for track in midi_file.tracks:
        absolute_ticks = 0
        for message in track:
            absolute_ticks += message.time
            if message.type == 'set_tempo':
                events.append((absolute_ticks, message.tempo))

    events.sort(key=lambda item: item[0])
    changes = [(0, 500000)]

    for ticks, tempo in events:
        if ticks == 0:
            changes[-1] = (0, tempo)
        else:
            changes.append((ticks, tempo))

    return changes


def tick_to_second(ticks, ticks_per_beat, tempo_changes):
    seconds = 0.0
    previous_ticks, previous_tempo = tempo_changes[0]

    for change_ticks, tempo in tempo_changes[1:]:
        if ticks <= change_ticks:
            break
        seconds += mido.tick2second(
            change_ticks - previous_ticks,
            ticks_per_beat,
            previous_tempo,
        )
        previous_ticks = change_ticks
        previous_tempo = tempo

    seconds += mido.tick2second(ticks - previous_ticks, ticks_per_beat, previous_tempo)
    return seconds


def collect_notes(midi_file):
    tempo_changes = collect_tempo_changes(midi_file)
    notes = []

    for track_index, track in enumerate(midi_file.tracks):
        active_notes = defaultdict(list)
        absolute_ticks = 0

        for message_index, message in enumerate(track):
            absolute_ticks += message.time

            if message.type == 'note_on' and message.velocity > 0:
                key = (message.channel, message.note)
                active_notes[key].append({
                    'track_index': track_index,
                    'start_index': message_index,
                    'start_ticks': absolute_ticks,
                    'start_seconds': tick_to_second(
                        absolute_ticks,
                        midi_file.ticks_per_beat,
                        tempo_changes,
                    ),
                    'note': message.note,
                    'velocity': message.velocity,
                    'start_message': message,
                })
            elif message.type in ('note_off', 'note_on'):
                key = (message.channel, message.note)
                if active_notes[key]:
                    start = active_notes[key].pop()
                    notes.append({
                        'track_index': track_index,
                        'start_index': start['start_index'],
                        'end_index': message_index,
                        'start_ticks': start['start_ticks'],
                        'start_seconds': start['start_seconds'],
                        'note': start['note'],
                        'velocity': start['velocity'],
                        'start_message': start['start_message'],
                        'end_message': message,
                        'hand': None,
                        'rule': None,
                    })

    notes.sort(key=lambda item: (item['start_seconds'], item['note']))
    return notes


def group_notes(notes):
    groups = []
    current = []
    group_start = None

    for note in notes:
        if not current:
            current = [note]
            group_start = note['start_seconds']
            continue

        if note['start_seconds'] - group_start <= GROUP_START_WINDOW_SECONDS:
            current.append(note)
        else:
            groups.append(current)
            current = [note]
            group_start = note['start_seconds']

    if current:
        groups.append(current)

    return groups


def assign_note(note, hand, rule_name, rule_counts):
    note['hand'] = hand
    note['rule'] = rule_name
    rule_counts[rule_name] += 1


def continuity_hand(note, last_left_pitch, last_right_pitch):
    if last_left_pitch is None or last_right_pitch is None:
        return None

    left_distance = abs(note['note'] - last_left_pitch)
    right_distance = abs(note['note'] - last_right_pitch)

    if right_distance - left_distance >= HAND_CONTINUITY_MARGIN:
        return 'left'
    if left_distance - right_distance >= HAND_CONTINUITY_MARGIN:
        return 'right'
    return None


def fallback_hand(note):
    if note['note'] < MIDDLE_SPLIT_PITCH:
        return 'left', 'middle_split_left'
    return 'right', 'middle_split_right'


def assign_group(group, last_left_pitch, last_right_pitch, rule_counts):
    for note in group:
        if note['note'] <= LEFT_STRONG_PITCH:
            assign_note(note, 'left', 'strong_left', rule_counts)
        elif note['note'] >= RIGHT_STRONG_PITCH:
            assign_note(note, 'right', 'strong_right', rule_counts)

    middle_notes = [note for note in group if note['hand'] is None]
    middle_notes.sort(key=lambda item: item['note'])

    if len(middle_notes) >= 2:
        split_index = len(middle_notes) // 2
        for index, note in enumerate(middle_notes):
            if len(middle_notes) % 2 == 1 and index == split_index:
                continue
            if index < split_index:
                assign_note(note, 'left', 'group_relative_left', rule_counts)
            else:
                assign_note(note, 'right', 'group_relative_right', rule_counts)

    for note in middle_notes:
        if note['hand'] is not None:
            continue

        hand = continuity_hand(note, last_left_pitch, last_right_pitch)
        if hand == 'left':
            assign_note(note, 'left', 'continuity_left', rule_counts)
        elif hand == 'right':
            assign_note(note, 'right', 'continuity_right', rule_counts)
        else:
            fallback, rule_name = fallback_hand(note)
            assign_note(note, fallback, rule_name, rule_counts)


def hand_span(notes):
    if len(notes) < 2:
        return 0
    pitches = [note['note'] for note in notes]
    return max(pitches) - min(pitches)


def average_pitch(notes):
    if not notes:
        return None
    return sum(note['note'] for note in notes) / len(notes)


def move_one_note_for_span(group, hand):
    hand_notes = [note for note in group if note['hand'] == hand]
    other_hand = 'right' if hand == 'left' else 'left'
    other_notes = [note for note in group if note['hand'] == other_hand]

    if hand_span(hand_notes) <= MAX_HAND_SPAN:
        return False

    other_average = average_pitch(other_notes)
    if other_average is None:
        candidate = max(hand_notes, key=lambda note: note['note']) if hand == 'left' else min(hand_notes, key=lambda note: note['note'])
    else:
        candidate = min(hand_notes, key=lambda note: abs(note['note'] - other_average))

    candidate['hand'] = other_hand
    return True


def apply_span_check(group):
    exceeded = False
    moved = 0

    for hand in ('left', 'right'):
        if hand_span([note for note in group if note['hand'] == hand]) > MAX_HAND_SPAN:
            exceeded = True
            if move_one_note_for_span(group, hand):
                moved += 1

    return exceeded, moved


def apply_channels(notes):
    for note in notes:
        channel = RIGHT_HAND_CHANNEL if note['hand'] == 'right' else LEFT_HAND_CHANNEL
        note['start_message'].channel = channel
        note['end_message'].channel = channel


def split_hands_in_place(midi_path):
    midi_file = mido.MidiFile(midi_path)
    notes = collect_notes(midi_file)
    groups = group_notes(notes)
    rule_counts = {rule_name: 0 for rule_name in RULE_ORDER}
    last_left_pitch = None
    last_right_pitch = None
    span_exceeded_groups = 0
    span_reassignments = 0

    for group in groups:
        assign_group(group, last_left_pitch, last_right_pitch, rule_counts)
        exceeded, moved = apply_span_check(group)
        if exceeded:
            span_exceeded_groups += 1
            span_reassignments += moved

        left_notes = [note for note in group if note['hand'] == 'left']
        right_notes = [note for note in group if note['hand'] == 'right']
        if left_notes:
            last_left_pitch = average_pitch(left_notes)
        if right_notes:
            last_right_pitch = average_pitch(right_notes)

    apply_channels(notes)
    midi_file.save(midi_path)

    right_notes = sum(1 for note in notes if note['hand'] == 'right')
    left_notes = sum(1 for note in notes if note['hand'] == 'left')

    stats = {
        'midi_path': midi_path,
        'total_notes': len(notes),
        'right_notes': right_notes,
        'left_notes': left_notes,
        'rule_counts': rule_counts,
        'span_exceeded_groups': span_exceeded_groups,
        'span_reassignments': span_reassignments,
    }
    return stats


def format_split_stats(stats):
    total_notes = stats['total_notes']
    lines = [
        'MIDI provisional hand split stats',
        'MIDI: {}'.format(stats['midi_path']),
        'Original notes: {}'.format(total_notes),
        'Channel 1 / right hand notes: {} ({:.2%})'.format(
            stats['right_notes'],
            stats['right_notes'] / total_notes if total_notes else 0.0,
        ),
        'Channel 3 / left hand notes: {} ({:.2%})'.format(
            stats['left_notes'],
            stats['left_notes'] / total_notes if total_notes else 0.0,
        ),
        'Rule assignments:',
    ]

    for rule_name in RULE_ORDER:
        count = stats['rule_counts'][rule_name]
        lines.append(
            '- {}: {} ({:.2%})'.format(
                RULE_LABELS[rule_name],
                count,
                count / total_notes if total_notes else 0.0,
            )
        )

    lines.extend([
        'Span exceeded groups: {}'.format(stats['span_exceeded_groups']),
        'Span reassignments: {}'.format(stats['span_reassignments']),
    ])
    return '\n'.join(lines)


def write_split_report(stats, report_path=None, append=False):
    report = format_split_stats(stats)
    if report_path:
        mode = 'a' if append else 'w'
        with open(report_path, mode, encoding='utf-8') as file:
            if append:
                file.write('\n\n')
            file.write(report)
            file.write('\n')

    print(report)
    if report_path:
        if append:
            print('Appending hand split report: {}'.format(report_path))
        else:
            print('Writing hand split report: {}'.format(report_path))


def apply_hand_split(midi_path, report_path=None, append_report=False):
    stats = split_hands_in_place(midi_path)
    write_split_report(stats, report_path=report_path, append=append_report)
    return stats


def choose_midi():
    root = tk.Tk()
    root.withdraw()
    return filedialog.askopenfilename(
        title='Choose cleaned MIDI to mark channels',
        filetypes=[
            ('MIDI files', '*.mid *.midi'),
            ('All files', '*.*'),
        ],
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mark provisional piano hand split by MIDI channel.')
    parser.add_argument('input_midi', nargs='?', help='Input MIDI file to modify in place.')
    parser.add_argument('--report', help='Optional report path.')
    parser.add_argument('--append-report', action='store_true', help='Append to report instead of overwriting.')
    args = parser.parse_args(argv)

    midi_path = args.input_midi or choose_midi()
    if not midi_path:
        print('No input selected.')
        return 1
    if not os.path.isfile(midi_path):
        messagebox.showerror('Hand Split', 'MIDI file does not exist.')
        return 1

    try:
        apply_hand_split(midi_path, report_path=args.report, append_report=args.append_report)
    except Exception as error:
        messagebox.showerror('Hand Split failed', str(error))
        raise

    if not args.input_midi:
        messagebox.showinfo('Hand Split complete', 'Updated in place:\n{}'.format(midi_path))
    return 0


if __name__ == '__main__':
    sys.exit(main())

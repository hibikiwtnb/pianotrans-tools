import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import torch

from bpmfix_utils import apply_bpm_fix, bpmfix_path_for
from clean_midi_rules import apply_rule_cleaning, cleaned_path_for
from hand_split_channels import apply_hand_split
from midi_stats import stats_path_for, write_midi_stats
from piano_transcription_inference import PianoTranscription, load_audio, sample_rate


AUDIO_EXTENSIONS = {'.flac', '.mp3', '.wav', '.ape', '.m4a', '.aif', '.aiff'}


def select_device():
    if torch.backends.mps.is_available():
        return torch.device('mps')
    if torch.cuda.is_available():
        return torch.device('cuda')
    return torch.device('cpu')


def midi_path_for(audio_path):
    filename, ext = os.path.splitext(audio_path)
    if ext.lower() not in AUDIO_EXTENSIONS:
        return None
    return filename + '.mid'


def transcribe_file(audio_path, transcriptor):
    midi_path = midi_path_for(audio_path)
    if not midi_path:
        print('Skip non-audio file: {}'.format(audio_path))
        return False

    if os.path.exists(midi_path):
        print('MIDI already exists: {}'.format(midi_path))
        if not os.path.exists(stats_path_for(midi_path)):
            write_midi_stats(midi_path)
        if not os.path.exists(bpmfix_path_for(midi_path)):
            bpmfix_path, _ = apply_bpm_fix(
                audio_path,
                midi_path,
                report_path=stats_path_for(midi_path),
                append_report=True,
            )
            cleaned_path, _, _ = apply_rule_cleaning(
                bpmfix_path,
                report_path=stats_path_for(midi_path),
                append_report=True,
            )
            apply_hand_split(
                cleaned_path,
                report_path=stats_path_for(midi_path),
                append_report=True,
            )
        elif not os.path.exists(cleaned_path_for(bpmfix_path_for(midi_path))):
            cleaned_path, _, _ = apply_rule_cleaning(
                bpmfix_path_for(midi_path),
                report_path=stats_path_for(midi_path),
                append_report=True,
            )
            apply_hand_split(
                cleaned_path,
                report_path=stats_path_for(midi_path),
                append_report=True,
            )
        return False

    print('Loading {}'.format(audio_path))
    audio, _ = load_audio(audio_path, sr=sample_rate, mono=True)
    print('Writing {}'.format(midi_path))
    transcriptor.transcribe(audio, midi_path)
    write_midi_stats(midi_path)
    bpmfix_path, _ = apply_bpm_fix(
        audio_path,
        midi_path,
        report_path=stats_path_for(midi_path),
        append_report=True,
    )
    cleaned_path, _, _ = apply_rule_cleaning(
        bpmfix_path,
        report_path=stats_path_for(midi_path),
        append_report=True,
    )
    apply_hand_split(
        cleaned_path,
        report_path=stats_path_for(midi_path),
        append_report=True,
    )
    return True


def collect_audio_files(path):
    if os.path.isfile(path):
        return [path]

    audio_files = []
    for name in sorted(os.listdir(path)):
        candidate = os.path.join(path, name)
        if os.path.isfile(candidate) and midi_path_for(candidate):
            audio_files.append(candidate)
    return audio_files


def choose_path():
    root = tk.Tk()
    root.withdraw()

    choice = messagebox.askyesnocancel(
        'Pianotrans',
        'Choose Yes for a single audio file, No for a folder batch.'
    )

    if choice is None:
        return None
    if choice:
        return filedialog.askopenfilename(
            filetypes=[
                ('Audio files', '*.flac *.mp3 *.wav *.ape *.m4a *.aif *.aiff'),
                ('All files', '*.*'),
            ]
        )
    return filedialog.askdirectory()


def main():
    print('--------------------------------------------------------------------------------')
    print('Pianotrans transcription script based on GiantMIDI-Piano')
    print('Choose a single audio file or a folder. MIDI files are written next to audio files.')
    print('--------------------------------------------------------------------------------')

    path = choose_path()
    if not path:
        print('No input selected.')
        return 1

    audio_files = collect_audio_files(path)
    if not audio_files:
        print('No supported audio files found.')
        return 1

    device = select_device()
    print('Using {} for inference.'.format(device))
    transcriptor = PianoTranscription(device=device)

    converted = 0
    for audio_path in audio_files:
        if transcribe_file(audio_path, transcriptor):
            converted += 1

    print('Done. Converted {} file(s).'.format(converted))
    return 0


if __name__ == '__main__':
    sys.exit(main())

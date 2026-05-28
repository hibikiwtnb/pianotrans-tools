# Pianotrans Run Tools
[English README](README_EN.md)

這個目錄包含 Pianotrans 轉錄入口，以及圍繞轉錄結果新增的 BPM 修正、MIDI 統計、保守規則清理、初步分手 / MIDI channel 標記、MIDI review 匯出工具。所有 `.command` 檔都可以直接雙擊執行。主入口使用 CUDA / CPU；另保留 Apple GPU / MPS 支持版入口供測試或對照。

## Main Pipeline

### `pianotrans.command`

完整轉錄流程入口。雙擊後直接選擇一個或多個音訊檔；MIDI 會寫在各音訊檔旁邊。

設備選擇順序：

```text
CUDA -> CPU
```

流程：

```text
Pianotrans inference
-> write original MIDI
-> write MIDI stats
-> detect BPM from source audio
-> write BPM-fixed MIDI
-> rule-based conservative cleanup
-> provisional hand split by MIDI channel
```

輸出檔案：

```text
song.mid
song_stats.txt
song_bpmfix.mid
song_bpmfix_cleaned.mid
```

`song_stats.txt` 會包含原始 MIDI 品質統計、BPMFix stats、cleaning stats，以及 hand-split stats。

如果 `song.mid` 已存在，流程不會重新轉錄；只會補缺失的 stats、BPM-fixed MIDI、cleaned MIDI。

### `pianotrans_mps.command`

保留的 Apple GPU / MPS 支持版入口，流程與 `pianotrans.command` 相同，但設備選擇順序為：

```text
MPS -> CUDA -> CPU
```

目前在 M2 MacBook Air 實測中，這個模型使用 MPS 反而比 CPU 慢，因此日常使用主入口 `pianotrans.command`。

## Standalone Tools

### `bpmfix.command`

只做 BPM 偵測和 MIDI BPM 修正。

使用方式：

1. 如果已知 BPM，在終端輸入 BPM。
2. 如果不知道 BPM，直接按 Return，然後選擇原音訊檔讓 Essentia 偵測固定 BPM。
3. 選擇要修正的 MIDI。
4. 輸出 `*_bpmfix.mid`。

自動偵測結果會記錄取整前 BPM，並把套用 BPM 四捨五入成整數；手動輸入的 BPM 會直接使用。

修正邏輯保留實際播放速度，只重算 MIDI ticks 和 tempo metadata：

```text
new_ticks = old_ticks * detected_bpm / 120
```

### `midi_stats.command`

只做 MIDI 品質統計。

使用方式：

1. 選擇 MIDI。
2. 輸出 `*_stats.txt`。

統計項目：

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

音高會同時輸出 MIDI note number 和英文音名，例如 `24 (C1)`。

### `clean_midi_rules.command`

只做第一階段保守規則清理。

使用方式：

1. 選擇 MIDI。
2. 輸出 `*_cleaned.mid`。
3. 輸出 `*_clean_report.txt`。

注意：獨立執行 `clean_midi_rules.command` 時會輸出 `*_clean_report.txt`；`pianotrans.command` pipeline 中，清理報告會追加寫入原本的 `song_stats.txt`。

清理規則只刪除高度疑似 artifact 的 note，不做音樂語義判斷、不分手、不量化、不判斷和弦/調性/旋律。

目前規則：

```text
duration < 0.03s
velocity < 20
velocity < 35 and duration < 0.08s
pitch outside 21-108
```

清理報告示例：

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

所有百分比都以 `Original notes` 為分母。

### `hand_split_channels.command`

只做初步左右手分配，直接在清理後 MIDI 上修改 note channel。

它不拆成多個 instrument track，也不刪除 note。

channel 對應：

```text
MIDI channel 1 = right hand
MIDI channel 3 = left hand
```

對 `mido` 這類 0-based channel 的 library 來說：

```text
channel 0 = MIDI channel 1
channel 2 = MIDI channel 3
```

這一步主要是為了讓 Logic Pro 樂譜視圖可以直接用 Piano 1 / Piano 3 顯示左右手，方便人工檢查和編輯。

### `generate_midi_review.py`

只讀取已完成後處理的 MIDI，輸出英文 Markdown 格式的 score facts table。它不修改 MIDI。

命令：

```bash
python generate_midi_review.py input.mid
```

預設輸出：

```text
midi_review.md
```

目前輸出結構：

```text
Global Info
Notes
```

詳細規格見：

```text
MIDI_REVIEW_SPEC.md
```

## Python Entrypoints

這些 `.command` 背後呼叫的 Python 腳本：

```text
pianotrans.py
pianotrans_mps.py
bpmfix.py
midi_stats_command.py
clean_midi_rules.py
hand_split_channels.py
generate_midi_review.py
```

共用 helper：

```text
bpmfix_utils.py
midi_stats.py
```

## Dependencies

Pianotrans 自己的 Python 環境：

```text
./.venv
```

Essentia BPM 偵測專用環境：

```text
$HOME/.local/share/pianotrans-bpm-env
```

全域 ffmpeg：

```text
$HOME/.local/bin/ffmpeg
```

模型權重預設位置：

```text
$HOME/piano_transcription_inference_data/note_F1=0.9677_pedal_F1=0.9186.pth
```

可覆蓋的環境變數：

```text
PIANOTRANS_BPM_ENV
PIANOTRANS_BPM_PYTHON
```

## Notes

- `pianotrans.py` 會依序嘗試 CUDA、CPU。
- `pianotrans_mps.py` 會依序嘗試 MPS、CUDA、CPU；在 Apple Silicon 且 PyTorch MPS 可用時會使用 Apple GPU。
- BPM 修正以固定 BPM 為前提，不建立 tempo map。
- 規則清理是低風險 preprocessing；後續更複雜的判斷應放在 feature extraction 或 ML classifier 等更高階流程中。

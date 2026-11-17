# NOVA

[![CI](https://github.com/mesubash/nova/actions/workflows/ci.yml/badge.svg)](https://github.com/mesubash/nova/actions/workflows/ci.yml)

A macOS-first personal AI voice assistant, built as a learning project on a MacBook Air M4.

**Status:** V1.3. A personal voice assistant for macOS with typed and spoken conversation in English and Nepali, a desktop window, confirmed desktop actions, and persistent notes, with measured safety and accuracy. Built as a learning project; see [docs/PLAN.md](docs/PLAN.md) and [docs/architecture.md](docs/architecture.md).

![NOVA desktop window](docs/images/nova-window.png)

## What works now

- Typed chat in the terminal with follow-up context (the last N exchanges are remembered).
- Clear messages for missing configuration, timeouts, network failures and API errors.
- Automatic retry (up to 3 attempts) when Gemini's servers are temporarily overloaded.
- `/exit`, Ctrl+D or Ctrl+C to quit; Ctrl+C while waiting cancels only that question.
- Answers are spoken aloud with macOS `say` while the text stays visible.
- Press Enter or type `/stop` to stop speaking.
- Press Enter on an empty line to ask by voice; press Enter again to stop recording.
- Recordings stop automatically after `NOVA_MAX_RECORDING_SECONDS`; silence is detected without calling the API.
- Desktop window (`nova-gui`) with transcript, hold-to-talk, stop speaking (Esc), and visible status; it stays responsive during requests.
- Desktop actions on request: open an allowed app, open a web page, or search file names in one approved folder. Anything with side effects is shown and confirmed first.
- Personal notes stored on your Mac: save, list, search, edit, and delete by asking.
- Optional local transcription with Whisper, so audio never leaves the Mac.
- Nepali and English mode: speak or type in Nepali, English, or a mix, and get answers in the same language. Devanagari answers are read by a Hindi voice.

## Performance

Measured on 2026-11-13 with `scripts/measure_latency.py` on a MacBook Air M4 over home Wi-Fi in Nepal, using `gemini-3.5-flash-lite` (8 runs; 1 further run hit the free-tier rate limit):

| Step | Median | Fastest | Slowest |
| --- | --- | --- | --- |
| Transcription | 2.27 s | 1.56 s | 2.55 s |
| Model reply | 1.21 s | 0.93 s | 2.13 s |
| Speech start | 0.01 s | 0.00 s | 0.01 s |
| **Total: release Talk → speech starts** | **3.40 s** | 2.70 s | 4.35 s |

"Speech start" is when the `say` process is launched, not when sound is first heard. Network conditions and Gemini's load change these numbers; rerun the script to measure your own setup. The packaged app is 134 MB, mostly the Qt framework.

### Local transcription (optional)

Transcribe voice questions on your Mac instead of with Gemini:

```bash
pip install -e ".[local]"
echo 'NOVA_TRANSCRIBER=local' >> .env
```

The first voice question downloads `whisper-large-v3-turbo` (about 1.6 GB) from Hugging Face into `~/.cache/huggingface`; after that, your audio never leaves the Mac. Measured back to back on the same day with identical audio:

| | Gemini transcription | Local transcription |
| --- | --- | --- |
| Transcription (median) | 1.66 s | 1.04 s |
| Total: release Talk → speech starts (median) | 2.85 s | 2.14 s |
| Failed runs (rate limit) | 2 of 9 | 0 of 9 |
| "leap year" heard correctly | 2 of 2 | 0 of 3 ("league year") |

Local is faster and steadier and halves Gemini usage; Gemini was more accurate on this small, synthetic-voice sample. Smaller models (`mlx-community/whisper-small-mlx`, `mlx-community/whisper-tiny-mlx`) are faster still and can be chosen with `NOVA_LOCAL_MODEL`.

On the developer's own voice (15 phrases, `scripts/voice_benchmark.py`), Gemini had a 6.1% word error rate and local Whisper 9.8%; see [docs/transcription-results.md](docs/transcription-results.md). Gemini therefore stays the default and recommended backend. Choose local transcription if you value privacy, speed, and lower API usage over the last few points of accuracy.

### Nepali and English (optional)

```bash
echo 'NOVA_SPEECH_LANGUAGE=ne' >> .env
```

In this mode NOVA transcribes Nepali, English, or a mix, and answers in the language of the question. Measured on the developer's own voice (12 phrases), Gemini had a 25.5% character error rate: ordinary questions were mostly exact, while commands that mix in English words were often misheard. Local Whisper reached 47.2% and is refused in this mode. See [docs/transcription-results-nepali.md](docs/transcription-results-nepali.md).

macOS has no Nepali voice, so Devanagari answers are read by a Hindi voice (`Lekha` by default, set with `NOVA_DEVANAGARI_VOICE`). If that voice is not installed, the answer is shown as text with an explanation.

## Limitations

- macOS on Apple Silicon only; tested on a MacBook Air M4.
- Requires an internet connection: chat always uses Gemini; transcription does too unless local transcription is selected.
- Gemini's free tier allows 15 requests per minute for this model, and a voice question uses two. When Gemini asks for a short wait (8 seconds or less), NOVA waits and retries once; otherwise it tells you how long to wait.
- Push-to-talk only: no wake word, and you cannot interrupt NOVA by speaking.
- One action per request. Action results and notes are not sent back to the model, so it cannot reason about them (for example, which file is newest).
- Note search matches keywords, not meaning.
- The API key is stored in a private file rather than the macOS Keychain.
- The app is not signed with a Developer ID or notarized.
- Local transcription is available when running from source only; the packaged app uses Gemini.
- Nepali transcription is less accurate than English, especially for commands that mix in English names; a misheard command still needs your confirmation before anything happens.

## Security

Gemini can only *propose* actions; NOVA validates every proposal (allowed apps, http and https URLs only, file-name search inside one approved folder, valid note numbers) and asks before anything with side effects. A live adversarial suite of 30 attack prompts, including prompt injection, found **0 violations**; see [docs/adversarial-results.md](docs/adversarial-results.md). Offline attack tests run in CI on every change.

## Requirements

- macOS. Tested on a MacBook Air M4 with macOS 27.2.1.
- Python 3.12
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)

## Setup

```bash
git clone https://github.com/mesubash/nova.git
cd nova
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install -e . --no-deps
cp .env.example .env
```

Then open `.env` and set `GEMINI_API_KEY` and `GEMINI_MODEL`.

## Configuration

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `GEMINI_API_KEY` | Yes | | Your Gemini API key |
| `GEMINI_MODEL` | Yes | | Model ID, for example `gemini-3.5-flash-lite` |
| `NOVA_REQUEST_TIMEOUT` | No | `30` | Seconds to wait for each request |
| `NOVA_MAX_HISTORY_TURNS` | No | `10` | Exchanges kept as conversation context |
| `NOVA_MAX_RECORDING_SECONDS` | No | `30` | Longest voice recording |
| `NOVA_ALLOWED_APPS` | No | `Safari,Notes,Calendar,Music,Calculator,TextEdit,Finder` | Apps NOVA may open |
| `NOVA_SEARCH_FOLDER` | No | off | Folder whose file names NOVA may search |
| `NOVA_DATA_DIR` | No | `~/Library/Application Support/NOVA` | Where notes are stored |
| `NOVA_TRANSCRIBER` | No | `gemini` | `gemini` or `local` |
| `NOVA_LOCAL_MODEL` | No | `mlx-community/whisper-large-v3-turbo` | Whisper model for local transcription |
| `NOVA_SPEECH_LANGUAGE` | No | `en` | `en`, or `ne` for Nepali and English |
| `NOVA_DEVANAGARI_VOICE` | No | `Lekha` | macOS voice for Devanagari answers |

## Run

```bash
nova
```

`python -m nova` also works.

For the desktop window:

```bash
nova-gui
```

## Build the macOS app

```bash
pip install -e ".[build]"
scripts/build_app.sh
open dist/NOVA.app
```

The app reads its settings from `~/Library/Application Support/NOVA/config.env`; on first launch without settings it offers to create and open that file.

The build is for Apple Silicon and is **not signed with a Developer ID or notarized**. An app you build yourself opens normally. If you download it instead, macOS will warn you: right-click the app and choose Open, or allow it in System Settings › Privacy & Security. macOS may ask for microphone access again after each rebuild.

## Development

GitHub Actions runs the same checks on every push and pull request (macOS, Python 3.12). See [docs/architecture.md](docs/architecture.md) for how the modules fit together.

```bash
pytest
ruff format --check .
ruff check .
```

The tests use fake clients and never call the real API. To measure real model latency on your machine (this makes billable API calls):

```bash
python scripts/benchmark_models.py
```

## Privacy

Everything you type or say, plus the current session's conversation history, is sent to Google's Gemini API; with local transcription, audio stays on the Mac and only the transcript is sent. NOVA does not save conversations or recordings to disk. Notes are stored only on your Mac and are never sent to Gemini, apart from what you say or type when asking to save or edit one. On Gemini's free tier, Google may use prompts to improve its products; check the current [Gemini API terms](https://ai.google.dev/gemini-api/terms) before sending anything private.

## Project layout

```text
src/nova/
├── __main__.py        # entry point and terminal chat loop
├── config.py          # configuration loading and validation
├── ai.py              # the only module that talks to Gemini
├── conversation.py    # bounded session history
├── speech.py          # recording and spoken output
├── transcription.py   # local Whisper transcription
├── storage.py         # SQLite notes
├── actions/           # validation and execution of proposed actions
└── ui/                # PySide6 desktop window
scripts/               # benchmarks, adversarial suite, app build
docs/
├── PLAN.md            # milestones and completion criteria
├── architecture.md    # how the modules fit together
└── decisions.md       # why things are built the way they are
```

## License

[MIT](LICENSE)
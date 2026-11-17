# Architecture

NOVA is a single Python package with a terminal interface (`nova`) and a desktop window (`nova-gui`). Both use the same core modules; the interfaces only handle input, output, and threading.

## Modules

| Module | Responsibility | Talks to |
| --- | --- | --- |
| `config.py` | Load and validate settings once at start-up | Environment, `.env`, `~/Library/Application Support/NOVA/config.env` |
| `ai.py` | The only module that calls Gemini: chat, transcription (with a Nepali and English prompt in Nepali mode), action proposals, retries | Gemini API |
| `transcription.py` | Choose the transcriber: Gemini, or Whisper on the Mac through MLX, loaded once and reused | `ai.py`, `mlx-whisper` (optional) |
| `conversation.py` | Bounded session history; records actions only after their outcome | A `Responder` (any object with `reply()`) |
| `speech.py` | Background speech with `say`, using a Hindi voice for Devanagari text; microphone recording with `sounddevice` | macOS `say`, microphone |
| `actions/` | Validate untrusted proposals, confirm, execute, report outcomes | `open`, filesystem, notes |
| `storage.py` | SQLite notes with stable IDs and transactions | `notes.db` in Application Support |
| `__main__.py` | Terminal loop | Everything above |
| `ui/` | PySide6 window and the background `TaskRunner` | Everything above |

## Request flow

```mermaid
flowchart LR
    User -->|types or speaks| Interface[Terminal or window]
    Interface -->|WAV audio| Transcribe[transcription.py]
    Transcribe -->|Gemini or local Whisper| Interface
    Interface -->|question| Conv[conversation.py]
    Conv -->|history| AI
    AI -->|answer text| Conv
    AI -->|ActionRequest, untrusted| Conv
    Conv --> Interface
    Interface -->|ActionRequest| Validate[actions.validate]
    Validate -->|typed action or rejection| Confirm{Side effects?}
    Confirm -->|read-only, or user said yes| Execute[actions.execute]
    Execute --> System[open, file search, notes]
    Execute -->|ActionResult| Interface
    Interface -->|actual outcome| Conv
    Interface -->|answer| Speech[speech.Speaker]
```

## Trust boundary

Model output is untrusted input. Gemini can only *propose* one of eight declared actions. `validate()` checks the action name, the exact set of arguments, their types and lengths, the app allowlist, URL schemes, and note IDs, and returns a typed action object or raises `ActionRejected`. `execute()` accepts only those typed objects, so raw model output cannot reach `subprocess`, the filesystem, or the database.

Actions with side effects (opening apps or URLs, saving, editing, deleting notes) always ask first, defaulting to No. This also covers misheard speech: a wrong transcript can at worst propose an action the user then sees and declines. Action results, file names, and stored notes are never sent back to Gemini, which also removes a prompt-injection path.

## Language and speech

`NOVA_SPEECH_LANGUAGE=ne` switches transcription to a prompt that expects Nepali, English, or a mix, writing Nepali in Devanagari and app names and command words in Latin script. Local Whisper is refused in this mode because it measured far worse on Nepali. Replies follow the language of the question. macOS has no Nepali voice, so `Speaker` reads any answer containing Devanagari with a Hindi voice (`Lekha` by default); it checks once that the voice is installed and otherwise raises `SpeechError`, so the answer stays on screen as text with an explanation.

## Retries

`ai.py` retries only failures that are safe to repeat, and never executes actions itself. Overloaded or unavailable servers are retried up to three attempts with growing delays. A rate limit is retried once, only when Gemini asks for a wait of 8 seconds or less; a longer wait, or a second rate limit right away, is reported with how long to wait.

## Threading

- **Terminal:** single-threaded, except `sounddevice`'s audio callback thread, which only appends audio chunks.
- **Window:** the Qt UI thread owns all widgets. `TaskRunner` runs one blocking task at a time (recording, transcription, Gemini requests, action execution) on a single worker thread and returns results through queued Qt signals. Cancelling advances a task number so late results are dropped.
- **Speech:** `say` runs as a separate process; the window polls it with a `QTimer`.
- **Notes:** each database operation opens its own SQLite connection, so it is safe from either thread.

## Data and privacy

| Data | Where it lives | Sent to Gemini? |
| --- | --- | --- |
| Typed questions and session history | Memory, cleared on exit | Yes |
| Voice recordings | Memory only, never written to disk | Yes with Gemini transcription; no with local transcription |
| Action results and file names | Shown on screen | No |
| Saved notes | `~/Library/Application Support/NOVA/notes.db` (mode 600) | No, except the text you say while saving or editing |
| API key | `config.env` in Application Support (mode 600) or `.env` (development), never logged | Used only to authenticate |

## Errors

Each layer raises its own error type with a message that is safe to show: `ConfigError`, `AIError` (with a `retryable` flag), `RecordingError`, `SpeechError`, `ActionRejected`, and `StorageError`. The interfaces turn these into visible messages and return to a usable state. Any other exception is treated as a bug and labelled as unexpected rather than hidden.

## Testing

Every external dependency is a parameter that tests replace with a fake: the Gemini client, `sleep`, `subprocess.Popen` and `subprocess.run`, the audio stream, the stop-recording wait, and the clock. SQLite and file search run against real files in temporary folders. The window is tested with pytest-qt, rendered off-screen. Tests never call the real API. Live measurements are separate scripts run on purpose: `benchmark_models.py` and `measure_latency.py` (speed), `voice_benchmark.py` (transcription accuracy on a real voice), `command_benchmark.py` (whether spoken Nepali commands lead to the right action), and `adversarial_actions.py` (attack prompts against validation). Each writes its results to `docs/`.

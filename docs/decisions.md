# Decision records

Short records of important choices and why they were made. Newest last.

## V0.1: Foundation and text conversation (2026-11-13)

**Python 3.12.** A conservative version supported by google-genai, PySide6 and PyInstaller.

**pip, venv and `requirements.lock`** instead of Poetry or uv. Fewer tools to learn. `pyproject.toml` declares acceptable version ranges; the lock file records the exact tested versions for reproducible installs.

**`src/` layout with an editable install.** Prevents accidentally importing the package from the working directory, so tests run against the installed package.

**One `ai.py` module owns all Gemini code.** The rest of NOVA uses its own `Message` type with `user`/`assistant` roles; `ai.py` translates `assistant` to Gemini's `model`. Swapping providers or adding a local model later touches one module. `Conversation` depends only on a `Responder` protocol (any object with `reply()`).

**`GEMINI_MODEL` is required, with no default.** Model names are renamed and retired often; a hardcoded default would go stale silently.

**Model: `gemini-3.5-flash-lite`.** Chosen by measurement with `scripts/benchmark_models.py` on 2026-11-13 (MacBook Air M4, Nepal, 3 runs each):

| Model | Median | Notes |
| --- | --- | --- |
| gemini-3.5-flash-lite | 1.2s | Consistent across all runs |
| gemini-3.1-flash-lite | 11.1s | Unstable, up to 32.7s |
| gemini-3.6-flash | n/a | 504 deadline exceeded |
| gemini-3.8-flash | n/a | 503 high demand |

Server load varies over time; rerun the benchmark before changing models.

**No thinking-level setting.** Low thinking made no measurable difference for Flash-Lite (1.2s vs 1.3s), so the extra setting was not added.

**Retry only transient server errors.** HTTP 500/502/503/504 are retried up to 3 attempts with 1s and 2s waits. Timeouts, 4xx errors and connection failures are not retried: a retry would either fail the same way or make the user wait another full timeout.

**Catch `httpx2` exceptions.** google-genai 3.x sends requests through httpx2; catching `httpx` exceptions would miss real timeouts and connection failures.

**Failed turns are not stored in history.** If a request fails or is cancelled with Ctrl+C, the unanswered question is not added, so the next request has a clean context.

## V0.2: Spoken output (2026-11-13)

**Text reaches `say` through stdin, never as an argument.** An argument list without a shell prevents command injection; stdin additionally prevents answer text from being read as a `say` option.

**Speech plays in the background with `Popen`.** The prompt returns immediately, so pressing Enter or typing `/stop` can interrupt playback. Starting a new question stops any current speech first.

**Text is printed before speech starts.** A speech failure therefore can never hide the answer.

**A system instruction asks for short spoken-style answers without markdown.** `to_speakable()` removes any remaining markdown symbols as a safety net.

## V0.3: Voice input (2026-11-13)

**Toggle push-to-talk in the terminal.** An empty Enter starts recording, Enter stops it. Hold-to-talk is deferred to the desktop window, because detecting a held key in a terminal needs Accessibility permission.

**`sounddevice` at 16 kHz mono.** Avoids PyAudio's installation problems on Apple Silicon; 16 kHz mono is the standard speech format and keeps uploads small (about 32 KB per second).

**Gemini transcribes the audio.** One provider and no extra dependency. A `[no speech]` marker lets the model report silence instead of inventing text; transcription uses `temperature=0` and no chat system instruction.

**Audio stays in memory.** It is encoded to WAV with `io.BytesIO` and never written to disk.

**Speech always stops before recording starts**, so NOVA cannot transcribe its own voice.

**Silence and permission checks before uploading.** A recording of exact zeros usually means macOS denied the microphone (it does not raise an error), so the user is pointed to Privacy & Security. A recording whose loudest sample is below `SILENCE_PEAK` (0.02) is treated as silence without calling the API. The threshold is a starting value to tune with measurements.

**Recording length is bounded** by `NOVA_MAX_RECORDING_SECONDS` (default 30), enforced in the audio callback; waiting for Enter uses `select` with the same timeout.

## V0.4: Desktop interface (2026-11-13)

**PySide6 window alongside the terminal app.** `nova-gui` opens the window and `nova` keeps the terminal interface; both use the same core modules.

**One background worker, results via Qt signals.** `TaskRunner` runs one blocking task at a time on a single thread, so requests cannot overlap and the UI thread is never blocked. Results return to the UI thread through queued signals; widgets are only touched there.

**Cancellation by task number.** Running threads cannot be stopped safely, so cancelling advances the current task number and results from older tasks are dropped when they arrive. Used for quick taps of Talk and when the window closes.

**Hold-to-talk reuses the terminal `Recorder`.** The window passes `threading.Event.wait` as the stop function; releasing the button sets the event. Presses shorter than 0.3 s are cancelled with a hint.

**One `set_state()` controls status text and enabled controls**, so the controls always match what NOVA is doing. Speaking is detected by polling the `say` process every 200 ms with a `QTimer`.

## V0.5: Controlled desktop actions (2026-11-13)

**The model proposes; the application decides.** Gemini function calling returns a structured `ActionRequest`, treated as untrusted input. `validate()` turns it into a typed `OpenApp`, `OpenUrl`, or `SearchFiles`, or rejects it. `execute()` only accepts those validated types, so raw model output can never reach `subprocess`.

**Validation rules.** Only three actions exist. Each requires exactly one non-empty string argument without control characters and with a bounded length. Apps must match `NOVA_ALLOWED_APPS` (case-insensitive; the configured spelling is executed). URLs must be http or https with a host and no spaces. Search accepts only a file-name fragment (no `/` or `\`) inside `NOVA_SEARCH_FOLDER`.

**Folder boundary after resolution.** Search does not enter symlinked folders, and every match is resolved and checked to remain inside the approved folder. Hidden files are skipped; at most 20,000 files are scanned and 20 results returned.

**No shell.** `open` is called with an argument list. URLs always begin with `http`, so they cannot be read as options.

**Confirmation for every action with side effects, every time.** Opening apps and URLs always asks, defaulting to No; read-only search does not ask. Session-wide "always allow" and a trusted-app list were considered and deferred: voice transcription can mishear, and explicit confirmation is the simplest guarantee for this release.

**Action results are not sent back to the model.** The outcome message is already exact, it avoids a second request, and file names from disk never reach Gemini, which removes a prompt-injection path. Trade-off: the model cannot reason about search results.

**History records what actually happened.** A proposed action is added to the conversation only after its outcome (opened, failed, rejected, or cancelled) is known. One action per turn.

## V0.6: Persistent notes (2026-11-13)

**SQLite in `~/Library/Application Support/NOVA/notes.db`.** The standard macOS location for app data, outside the repository so notes can never be committed. Overridable with `NOVA_DATA_DIR`. The folder is created on first use with mode 700 and the database file is set to 600.

**Stable IDs.** `INTEGER PRIMARY KEY AUTOINCREMENT` never reuses a deleted note's number, so "note 3" always means the same note.

**No silent data loss.** Each operation opens its own connection inside a transaction: it commits on success and rolls back on any error. Updates and deletes that match no row raise `NoteNotFound` instead of reporting success. All database errors become a visible `StorageError`; if the database cannot be opened, NOVA starts with notes disabled and says so.

**One connection per operation.** Avoids SQLite's same-thread restriction, since the window executes actions on a background thread.

**Keyword search.** Every word must appear, ignoring case. `%` and `_` are escaped so they match literally. All values use `?` placeholders; the only SQL built with string formatting is fixed text written in the code.

**Notes use the action pipeline.** Five actions (save, list, search, edit, delete) reuse V0.5's validate, confirm, execute flow. Saving, editing, and deleting always ask first; listing and searching are read-only. Edit and delete check that the note exists during validation, so confirmations show the note's current text and never refer to a missing note.

**Explicit saving only.** Notes are saved only through a confirmed `save_note`; nothing is inferred or stored automatically.

**Stored notes are never sent to Gemini.** Listing and searching run locally and the results are not returned to the model. The only note text Gemini receives is what the user says or types while asking to save or edit a note.

## V1.0: Portfolio release (2026-11-13)

**CI on macOS.** GitHub Actions runs `ruff format --check`, `ruff check`, and `pytest` on every push to `main` and every pull request, on Apple Silicon, installing from `requirements.lock` exactly as the README describes.

**Settings for the packaged app.** A `.app` launched from Finder has no shell environment and starts in `/`, so settings are also read from `~/Library/Application Support/NOVA/config.env`. Precedence: process environment, then project `.env`, then the user file. The file is created atomically with mode 600 and its permissions are tightened if loosened. The macOS Keychain would be stronger and remains a possible improvement.

**PyInstaller, Apple Silicon only, ad-hoc signed.** The build is defined in `packaging/nova.spec`. `Info.plist` includes `NSMicrophoneUsageDescription`, without which macOS silently denies the microphone. The app is not signed with a Developer ID or notarized.

**Latency measured, not estimated.** `scripts/measure_latency.py` replays questions generated with `say` as 16 kHz WAV through the real pipeline. Median total wait after releasing Talk: 3.40 s (2.70 to 4.35 s); transcription is the largest share. "Speech start" measures when `say` is launched, not when sound is first heard.

**Rate limits are reported, not retried.** HTTP 429 is a client error and is shown to the user. On the free tier (15 requests per minute for `gemini-3.5-flash-lite`), a voice question uses two requests.

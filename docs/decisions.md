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

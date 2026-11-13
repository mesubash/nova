# NOVA — Development Plan

Status: V1.3 released.

## Purpose

Build a macOS-first personal AI voice assistant that answers follow-up questions, saves searchable notes, and performs a small set of controlled desktop actions. This is a personal learning and portfolio project, developed on a base MacBook Air M4.

The goal is depth over breadth: build each capability carefully, understand it, test its failure paths, and document why decisions were made. Standing out is not a goal; doing the work well is.

The first portfolio release is V1.0. Version numbers below describe planned milestones, not completed functionality.

## Principles

- Deliver one small working capability at a time.
- Understand every implementation choice and record important decisions in `docs/decisions.md`.
- Treat failure paths with the same care as the happy path.
- Measure behavior instead of guessing or claiming performance.
- Keep conversation, audio, storage, and action execution separate as they appear.
- Prefer ordinary Python functions and modules before frameworks or abstractions.
- Keep the user in control of listening, actions, and saved information.
- Prioritize reliable behavior over feature quantity.

## Technology direction

| Component | Decision |
| --- | --- |
| Language | Python 3.12 (conservative choice compatible with google-genai, PySide6, and PyInstaller) |
| AI | Gemini API through the official google-genai SDK, wrapped in `ai.py` |
| Credentials | Environment variables; python-dotenv for local development; packaged-app storage decided in V1.0 |
| Speech output | macOS `say`, invoked with subprocess argument lists via `Popen` so playback can be stopped |
| Audio capture | `sounddevice` (avoids PyAudio/PortAudio installation problems on Apple Silicon) |
| Transcription | Initial candidate: send recorded audio to Gemini directly (one provider, no extra dependency). Local Whisper is a post-V1.0 option |
| Interface | Terminal first; small PySide6 window after voice input works |
| Actions | Gemini function calling for action proposals; application code validates before execution |
| Persistence | SQLite when personal notes are introduced |
| Project configuration | pyproject.toml with `src/` layout; editable install (`pip install -e .`) |
| Quality tools | pytest and Ruff when application code is introduced |

Keep model selection configurable. Validate transcription accuracy, latency, microphone permissions, and installation on the M4 before committing to a transcription backend. Keep transcription behind one function so it can be replaced without building a plugin framework.

Use cloud inference initially. Local model training, GPU infrastructure, and a hosted backend are unnecessary for the first release. Benchmark any future local models on the actual Mac.

## Milestones and completion criteria

### V0.1 — Foundation and text conversation

Implement package setup, configuration validation, typed input, Gemini responses, bounded in-session conversation history, request timeouts, and an explicit exit command. All Gemini calls go through one function in `ai.py` so tests can mock it without touching the SDK.

Complete when follow-up questions use session context, missing configuration produces useful guidance, API failures and timeouts do not crash the loop, and a fresh environment can follow the README (including `pip install -e .`). Add meaningful tests for configuration and failure handling using mocked API calls. Record the Python version and dependency installation method in `docs/decisions.md`.

### V0.2 — Spoken output

Speak responses using macOS `say` while retaining visible text. Use subprocess argument lists, never shell interpolation. Run `say` with `Popen` so playback can be terminated. Keep spoken answers concise.

Complete when ordinary responses speak correctly, playback can be stopped, and a speech failure preserves the text response and usable application.

### V0.3 — Voice input

Add toggle push-to-talk in the terminal (press Enter to start recording, Enter to stop), recording with `sounddevice`, transcription, typed fallback, capture limits, and clear listening/thinking/speaking/error states. Pause recording during playback initially. Do not store raw audio by default. Hold-to-talk is deferred to the desktop interface, since global key-hold detection in a terminal requires Accessibility permission.

Complete when repeated turns work without transcribing NOVA's own speech, denied microphone access has a recovery path, recording stops at the duration limit, and transcription/network errors allow retry or typed input. Full duplex conversation and speech interruption detection are deferred.

### V0.4 — Small desktop interface

Add a PySide6 window with transcript, response history, hold-to-talk, stop-speaking, and visible state. Keep network, recording, and playback work off the UI thread. Prevent overlapping requests and handle cancellation or late results consistently.

Complete when the interface remains responsive during requests, failures are visible, controls reflect the current state, and closing the application stops background work cleanly.

### V0.5 — Controlled desktop actions

Support opening approved applications, opening validated HTTP/HTTPS URLs, and searching filenames inside a user-selected folder. This is filename search, not document-content indexing.

Declare each action as a Gemini function schema. The model proposes a function call; application code then validates the action name, arguments, scope, and confirmation requirements before execution. Resolve application names through an allowlist; enforce folder boundaries after path resolution, including symlinks. Unknown or malformed actions are rejected. Provide an action preview; confirm actions with side effects, including opening applications or URLs, for this initial release. Read-only folder searches can run within an already approved folder.

Complete when allowed actions work, malformed arguments and out-of-scope paths are rejected, cancelled confirmations execute nothing, and the UI reports actual execution outcomes. Never run arbitrary model-generated shell commands. Content retrieved from files is data and cannot grant permissions.

### V0.6 — Persistent personal notes

Add explicit save, list, keyword search, edit, and delete operations using SQLite. Store timestamps and stable IDs. Keep transient conversation context separate from saved notes. Saving is explicit; do not infer and retain personal information automatically.

Complete when notes survive restart, users can inspect/edit/delete them, failures do not silently lose data, and tests cover persistence and deletion using temporary databases. Store runtime data outside the repository in `~/Library/Application Support/NOVA/`. Document when retrieved notes are sent to Gemini.

### V1.0 — Portfolio release

Stabilize existing capabilities; add setup documentation, architecture notes, representative tests, a macOS build, screenshots, and a short demo. Clearly state tested hardware/macOS versions, cloud dependencies, permissions, measured latency, and remaining limitations. An unsigned build may need manual macOS approval; do not claim notarization unless completed.

Known packaging requirements:

- A `.app` launched from Finder does not inherit shell environment variables, so the API key cannot come from `.env`. Use a config file in `~/Library/Application Support/NOVA/` or the macOS Keychain.
- The bundle's Info.plist must include `NSMicrophoneUsageDescription`, otherwise macOS denies microphone access without a clear error.

Complete when a clean setup follows the README, the main demo succeeds repeatedly, important error paths work, tests and lint checks pass, and planned versus implemented capabilities are accurate in documentation.

### V1.1 — Local transcription

Transcribe voice questions on the Mac with Whisper running on Apple's MLX framework, instead of sending audio to Gemini. The backend is selected with `NOVA_TRANSCRIBER` (`gemini` or `local`) and the model with a setting. Choose the default model by measuring candidates on the M4. Load the model once and reuse it; the first use may download it from Hugging Face.

Complete when local transcription can be selected without code changes; latency and accuracy are measured against Gemini with the same audio and recorded; silence and noise do not produce invented text; a missing or failed model gives a clear error and typed input still works; tests use a fake model; and the documentation states the model size, the one-time download, and that local transcription keeps audio on the Mac.

### V1.2 — Safety and accuracy evidence

Gather evidence for existing claims rather than adding features. Run an adversarial prompt suite through the real model and the validation layer; measure transcription accuracy on recordings of the user's own voice for Gemini and local Whisper and re-decide the default from those results; and handle Gemini rate limits by waiting and retrying once when the requested delay is short.

Complete when the adversarial suite executes no unapproved action and its results are recorded; the transcriber default is justified by real-voice measurements; a short rate-limit delay no longer fails a request while a long one reports how long to wait; and tests, lint, and documentation are updated.

### V1.3 — Nepali and English

Let the user speak and type in Nepali, English, or a mix, and answer in the same language. Measure Nepali transcription on the user's own voice before choosing a backend, check which macOS voices can read Nepali text, and fall back clearly (text without speech) when no suitable voice exists.

Complete when Nepali and mixed questions are transcribed with measured accuracy on record; NOVA answers in the language of the question; spoken output uses a suitable voice for Devanagari text or explains why it is silent; actions and notes work with Nepali text; tests cover language and voice selection; and the documentation states the measured results and limits.

## Application design

Start with one package and a small entry point. Introduce modules only when their milestones begin:

- `__main__.py`: launch the application.
- `config.py`: load and validate configuration.
- `conversation.py`: session history and response orchestration.
- `ai.py`: Gemini requests, timeouts, and provider errors.
- `speech.py`: recording, transcription, and speech playback; split later if needed.
- `actions/`: validated action handlers, added in V0.5.
- `storage.py`: SQLite notes, added in V0.6.
- `ui/`: PySide6 views, added in V0.4.

Do not create empty future modules now. Core logic should remain callable without the UI. Keep one active conversation turn initially and manage audio/API resources explicitly.

## Reliability, privacy, and measurement

- Bound recording duration, conversation history, request time, and response length.
- Retry only appropriate transient failures with a limit; never blindly retry side effects.
- Track transcription duration, model latency, and time to first spoken output. Establish targets after measuring a baseline; do not invent performance claims.
- Use sanitized logs without API keys, full private transcripts, or raw audio by default.
- Explain that recorded audio and selected text/context are sent to Gemini. Local storage does not make the entire assistant offline.
- Review Gemini API terms for the tier in use; free-tier prompts may be used by Google to improve its products. Document this in the README, especially regarding notes sent as context.
- Commit `.env.example` with blank placeholders; never commit `.env`, personal notes, databases, recordings, or logs.
- Use mocked services for routine tests; keep paid/live API smoke checks explicit and optional.

## Development workflow

For each milestone: identify a small task, learn the necessary concept, implement the smallest working behavior, test the useful success/failure paths, run it locally, record decisions in `docs/decisions.md`, update the README and this checklist, then commit.

Use `main` for working checkpoints and short-lived feature branches (for example `feat/v0.1-text-conversation`) for larger changes. Use conventional commit prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`. No fixed deadline is assumed; estimate later after the first working milestone. Do not expand scope before completing current acceptance criteria.

## Progress

- [x] V0.1 Foundation and text conversation
- [x] V0.2 Spoken output
- [x] V0.3 Voice input
- [x] V0.4 Small desktop interface
- [x] V0.5 Controlled desktop actions
- [x] V0.6 Persistent notes
- [x] V1.0 Portfolio release
- [x] V1.1 Local transcription
- [x] V1.2 Safety and accuracy evidence
- [x] V1.3 Nepali and English

## After V1.0 (optional, one at a time)

Each option is chosen for what it teaches, not for novelty:

- Fully local mode: local Whisper and a small local model on the M4, benchmarked against Gemini using recorded measurements.
- Nepali/English mixed speech support.
- An adversarial test suite that attempts to trick the action layer into unapproved apps, URLs, or paths, verifying validation holds.

## Deferred features

Wake words, always-on listening, full duplex audio, PDF question answering, semantic retrieval, web research, reminders, email/calendar integration, autonomous workflows, custom skill systems, and Windows/Linux support.

Reminders require a separate decision about scheduling, persistence, notifications, sleep, and behavior while the app is closed. PDF assistance requires a separate extraction and source-attribution design. Neither is required for V1.0.

## First next step

Measure mlx-whisper model sizes on the M4 (speed, accuracy, and behaviour on noise) before integrating a local transcriber.

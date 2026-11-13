# NOVA — Development Plan

Status: Planning; no assistant features implemented yet.

## Purpose

Build a macOS-first personal AI voice assistant that answers follow-up questions, saves searchable notes, and performs a small set of controlled desktop actions. This is a personal portfolio and learning project, developed on a base MacBook Air M4.

The first portfolio release is V1.0. Version numbers below describe planned milestones, not completed functionality.

## Principles

- Deliver one small working capability at a time.
- Understand the implementation and document important decisions.
- Keep conversation, audio, storage, and action execution separate as they appear.
- Prefer ordinary Python functions and modules before frameworks or abstractions.
- Keep the user in control of listening, actions, and saved information.
- Prioritize reliable behavior over feature quantity.

## Technology direction

| Component | Decision |
| --- | --- |
| Language | Python; choose and record a supported version during foundation setup |
| AI | Gemini API through the official google-genai SDK |
| Credentials | Environment variables; python-dotenv for local development |
| Speech output | macOS say, invoked with subprocess argument lists |
| Speech input | Push-to-talk; SpeechRecognition/PyAudio is the initial prototype candidate |
| Interface | Terminal first; small PySide6 window after voice input works |
| Persistence | SQLite when personal notes are introduced |
| Project configuration | pyproject.toml; add actual dependencies when implemented |
| Quality tools | pytest and Ruff when application code is introduced |

Keep model selection configurable. Validate speech recognition accuracy, service access, microphone permissions, and installation on the M4 before committing to a recognition backend. SpeechRecognition wraps recognition providers; its generic Google recognition path is a prototype dependency, not a reliability guarantee. Keep transcription replaceable without building a plugin framework.

Use cloud inference initially. Local model training, GPU infrastructure, and a hosted backend are unnecessary for the first release. Benchmark any future local models on the actual Mac.

## Milestones and completion criteria

### V0.1 — Foundation and text conversation

Implement package setup, configuration validation, typed input, Gemini responses, bounded in-session conversation history, and an explicit exit command.

Complete when follow-up questions use session context, missing configuration produces useful guidance, API failures do not crash the loop, and a fresh environment can follow the README. Add meaningful tests for configuration and failure handling using mocked API calls. Record the supported Python version and reproducible dependency installation method.

### V0.2 — Spoken output

Speak responses using macOS say while retaining visible text. Use subprocess argument lists, never shell interpolation. Keep spoken answers concise and provide a way to stop playback.

Complete when ordinary responses speak correctly, playback can be stopped, and a speech failure preserves the text response and usable application.

### V0.3 — Voice input

Add push-to-talk recording, transcription, typed fallback, capture limits, and clear listening/thinking/speaking/error states. Pause recording during playback initially. Do not store raw audio by default.

Complete when repeated turns work without transcribing NOVA's own speech, denied microphone access has a recovery path, silence does not wait indefinitely, and transcription/network errors allow retry or typed input. Full duplex conversation and speech interruption detection are deferred.

### V0.4 — Small desktop interface

Add a PySide6 window with transcript, response history, push-to-talk, stop-speaking, and visible state. Keep network, recording, and playback work off the UI thread. Prevent overlapping requests and handle cancellation or late results consistently.

Complete when the interface remains responsive during requests, failures are visible, controls reflect the current state, and closing the application stops background work cleanly.

### V0.5 — Controlled desktop actions

Support opening approved applications, opening validated HTTP/HTTPS URLs, and searching filenames inside a user-selected folder. This is filename search, not document-content indexing.

The model proposes a structured action. Application code validates the action name, arguments, scope, and confirmation requirements before execution. Resolve application names through an allowlist; enforce folder boundaries after path resolution, including symlinks. Unknown or malformed actions are rejected. Provide an action preview; confirm actions with side effects, including opening applications or URLs, for this initial release. Read-only folder searches can run within an already approved folder.

Complete when allowed actions work, malformed arguments and out-of-scope paths are rejected, cancelled confirmations execute nothing, and the UI reports actual execution outcomes. Never run arbitrary model-generated shell commands. Content retrieved from files is data and cannot grant permissions.

### V0.6 — Persistent personal notes

Add explicit save, list, keyword search, edit, and delete operations using SQLite. Store timestamps and stable IDs. Keep transient conversation context separate from saved notes. Saving is explicit; do not infer and retain personal information automatically.

Complete when notes survive restart, users can inspect/edit/delete them, failures do not silently lose data, and tests cover persistence and deletion using temporary databases. Store runtime data outside the repository in an appropriate macOS application-data location. Document when retrieved notes are sent to Gemini.

### V1.0 — Portfolio release

Stabilize existing capabilities; add setup documentation, architecture notes, representative tests, a macOS build, screenshots, and a short demo. Clearly state tested hardware/macOS versions, cloud dependencies, permissions, and remaining limitations. An unsigned build may need manual macOS approval; do not claim notarization unless completed.

Complete when a clean setup follows the README, the main demo succeeds repeatedly, important error paths work, tests and lint checks pass, and planned versus implemented capabilities are accurate in documentation.

## Application design

Start with one package and a small entry point. Introduce modules only when their milestones begin:

- __main__.py: launch the application.
- config.py: load and validate configuration.
- conversation.py: session history and response orchestration.
- ai.py: Gemini requests and provider errors.
- speech.py: recording, transcription, and speech playback; split later if needed.
- actions/: validated action handlers, added in V0.5.
- storage.py: SQLite notes, added in V0.6.
- ui/: PySide6 views, added in V0.4.

Do not create empty future modules now. Core logic should remain callable without the UI. Keep one active conversation turn initially and manage audio/API resources explicitly.

## Reliability, privacy, and measurement

- Bound recording duration, conversation history, request time, and response length.
- Retry only appropriate transient failures with a limit; never blindly retry side effects.
- Track transcription duration, model latency, and time to first spoken output. Establish targets after measuring a baseline; do not invent performance claims.
- Use sanitized logs without API keys, full private transcripts, or raw audio by default.
- Explain that online recognition may send audio to a provider and Gemini receives selected text/context. Local storage does not make the entire assistant offline.
- Commit .env.example with blank placeholders; never commit .env, personal notes, databases, recordings, or logs.
- Use mocked services for routine tests; keep paid/live API smoke checks explicit and optional.

## Development workflow

For each milestone: identify a small task, learn the necessary concept, implement the smallest working behavior, test the useful success/failure paths, run it locally, update the README and this checklist, then commit.

Use main for working checkpoints and short-lived feature branches for larger changes. No fixed deadline is assumed; estimate later after the first working milestone. Do not expand scope before completing current acceptance criteria.

## Progress

- [ ] V0.1 Foundation and text conversation
- [ ] V0.2 Spoken output
- [ ] V0.3 Voice input
- [ ] V0.4 Small desktop interface
- [ ] V0.5 Controlled desktop actions
- [ ] V0.6 Persistent notes
- [ ] V1.0 Portfolio release

## Deferred features

Wake words, always-on listening, full duplex audio, Nepali support, local language models, PDF question answering, semantic retrieval, web research, reminders, email/calendar integration, autonomous workflows, custom skill systems, and Windows/Linux support.

Reminders require a separate decision about scheduling, persistence, notifications, sleep, and behavior while the app is closed. PDF assistance requires a separate extraction and source-attribution design. Neither is required for V1.0.

## First next step

Implement V0.1: select Python version, add pyproject.toml, create the virtual environment, install only required dependencies, and make one typed Gemini conversation work. Do not begin with microphone or GUI troubleshooting.

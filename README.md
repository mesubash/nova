# NOVA

A macOS-first personal AI voice assistant, built as a learning project on a MacBook Air M4.

**Status:** V0.1, typed conversation with Gemini in the terminal. Voice, a desktop window, desktop actions and personal notes are planned; see [docs/PLAN.md](docs/PLAN.md).

## What works now

- Typed chat in the terminal with follow-up context (the last N exchanges are remembered).
- Clear messages for missing configuration, timeouts, network failures and API errors.
- Automatic retry (up to 3 attempts) when Gemini's servers are temporarily overloaded.
- `/exit`, Ctrl+D or Ctrl+C to quit; Ctrl+C while waiting cancels only that question.
- Answers are spoken aloud with macOS `say` while the text stays visible.
- Press Enter or type `/stop` to stop speaking.

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

## Run

```bash
nova
```

`python -m nova` also works.

## Development

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

Everything you type, plus the current session's conversation history, is sent to Google's Gemini API. NOVA does not save conversations to disk. On Gemini's free tier, Google may use prompts to improve its products; check the current [Gemini API terms](https://ai.google.dev/gemini-api/terms) before sending anything private.

## Project layout

```text
src/nova/
├── __main__.py      # entry point and chat loop
├── config.py        # configuration loading and validation
├── ai.py            # the only module that talks to Gemini
└── conversation.py  # bounded session history
docs/
├── PLAN.md          # milestones and completion criteria
└── decisions.md     # why things are built the way they are
```

## License

MIT
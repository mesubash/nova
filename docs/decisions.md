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
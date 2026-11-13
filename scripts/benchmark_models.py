"""Compare Gemini model latency on this machine. Makes real (billable) API calls."""

import statistics
import time

from google import genai
from google.genai import types

from nova.config import load_config

MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
]
THINKING_LEVELS = [None, "low"]
PROMPT = "In two sentences, what is the capital of Nepal and why is it notable?"
RUNS = 3


def time_one(client: genai.Client, model: str, level: str | None) -> float:
    config = None
    if level:
        config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level=level)
        )
    start = time.monotonic()
    client.models.generate_content(model=model, contents=PROMPT, config=config)
    return time.monotonic() - start


def main() -> None:
    config = load_config()
    options = types.HttpOptions(timeout=int(config.request_timeout_seconds * 1000))
    with genai.Client(api_key=config.api_key, http_options=options) as client:
        for model in MODELS:
            for level in THINKING_LEVELS:
                label = f"{model} [thinking={level or 'default'}]"
                try:
                    times = [time_one(client, model, level) for _ in range(RUNS)]
                except Exception as exc:
                    print(f"{label:48} FAILED: {type(exc).__name__}: {exc}")
                    continue
                runs = ", ".join(f"{t:.1f}" for t in times)
                print(f"{label:48} median {statistics.median(times):5.1f}s   runs: {runs}")


if __name__ == "__main__":
    main()

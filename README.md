# NOVA

A macOS-first personal AI voice assistant built with Python and Google Gemini.

## Status

Planning and initial setup. Assistant functionality is not implemented yet.

## Planned capabilities

- Context-aware text and voice conversations
- Spoken responses and push-to-talk input
- A lightweight desktop interface
- Controlled desktop actions
- Persistent, searchable personal notes

## Development

NOVA grows through small, working milestones. See [the development plan](docs/PLAN.md) for scope, technology decisions, and completion criteria.

Application code will live in `src/nova/` and automated tests in `tests/`. Dependency and run instructions will be added with the first implementation.

## Configuration and privacy

Copy `.env.example` to `.env` when implementing local configuration. Supply your own API key and chosen model. Never commit credentials or personal runtime data. Planned online AI and speech services require internet access and may receive conversation text or audio.

## License

MIT. See `LICENSE` in the repository.

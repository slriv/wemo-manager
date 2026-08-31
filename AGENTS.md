# AGENTS.md

Shared instructions for AI coding assistants (Claude Code, GitHub Copilot, etc.) working
in this repository. Keep this file environment-agnostic: it's checked into version
control and read on every contributor's machine and in CI, none of which share a dev or
deployment setup. Don't add absolute paths, hostnames, IP addresses, ports, or credentials
here — use the environment variables documented in `README.md` instead.

## Project

Self-hosted FastAPI + SQLAlchemy/SQLite web app for discovering and controlling Belkin
WeMo devices via `pywemo`. See `README.md` for features, configuration, and the API
surface — don't duplicate that here.

## Layout

```text
app/
  main.py        Application entry point, lifespan, static mount
  database.py    Engine, session, schema creation
  models/        SQLAlchemy models
  schemas.py     Pydantic request and response models
  routers/       HTTP routes: devices, setup, UI pages
  services/      Discovery, device manager, repository, rules, settings, events
  templates/     Jinja2 templates
  static/        Stylesheet, scripts, staged APK
mobile/          Capacitor Android application
tests/           Test suite
```

## Setup, run, test

Use the `Makefile` targets rather than inventing commands:

- `make install` — create `.venv`, install with dev dependencies.
- `make run` — foreground dev server with autoreload.
- `make test` — run the pytest suite.
- `make help` — list all targets.

Always run `make test` after changing `app/` code before considering a change done.

## Code style

- Python 3.11+, `from __future__ import annotations` at the top of every module.
- Modern type hints everywhere (`str | None`, `list[dict]`, not `Optional`/`List`).
- One-line module/function docstrings only when the *why* isn't obvious from the name;
  no multi-paragraph docstrings.
- No comments that just restate the code. A comment is for a non-obvious constraint or
  workaround (see `_acquire_singleton_lock` in `app/main.py` for the pattern).
- No linter/formatter is currently configured in this repo — match the surrounding file's
  style rather than reformatting wholesale.
- Only update README.md when we are committing our changes when a change is necessary.
- all code should be tight, optimized, 
- no duplicate code, 
- no functions just wrapping a call to another function, 
- no narration in comments, 
- don't preserve back-ward compatibility.

## Testing conventions

- Tests live in `tests/`, one file per module under test (`test_<module>.py`).
- The suite substitutes a stub for `pywemo` so tests run without physical WeMo devices —
  don't write tests that require real hardware or real network access.
- Prefer testing through `app/services/` and `app/routers/` interfaces over reaching into
  device internals.
- only run tests when we commit. 

## Things to keep in mind

- The app has **no authentication** and stores Wi-Fi credentials in plaintext by design
  (LAN-only tool; see README "Configuration"). Don't add auth or encryption unprompted —
  raise it as a question if a change seems to need it.
- Only one app instance may run against a set of devices at a time, enforced by a file
  lock (`app/main.py`). Don't remove or bypass this locking.
- `deploy.sh` and `docker-compose.yml` describe a deployment shape (host networking,
  volume-mounted `/data`) that differs per site — don't hardcode assumptions from them
  into application code.

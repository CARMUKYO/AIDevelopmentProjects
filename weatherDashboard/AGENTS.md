# AGENTS.md — Weather Dashboard

Guidance for AI coding agents working in this repository. Read this fully before
making changes.

## Project purpose

A learning project: a terminal weather dashboard that consumes the public
[Open-Meteo](https://open-meteo.com/) API. The code exists to practise:

- External API integration (geocoding + forecast endpoints)
- JSON parsing and schema validation
- HTTP clients (timeouts, retries, connection reuse)
- API failures and timeouts
- Configuration management (defaults → file → env → CLI flags)
- Handling unexpected / malformed responses
- Mocking external APIs in tests (no real network in the test suite)

Correctness and clarity of these concerns matter more than features or UI polish.

## Stack (fixed — do not change without asking)

| Concern            | Choice                                          |
| ------------------ | ----------------------------------------------- |
| Language           | Python 3.11+                                    |
| HTTP client        | `httpx` (sync `httpx.Client`)                   |
| JSON validation    | `pydantic` v2 models                            |
| Configuration      | `pydantic-settings` + optional TOML file        |
| CLI                | `typer`                                         |
| Rendering          | `rich` (tables/panels)                          |
| Tests              | `pytest` + `respx` (httpx mocking)              |
| Lint / format      | `ruff` (lint + format), `mypy --strict` on `src`|
| Packaging          | `pyproject.toml`, `src/` layout, `uv` or `pip`  |

Do not add new runtime dependencies without asking the user first.

## External API

- Geocoding: `GET https://geocoding-api.open-meteo.com/v1/search?name=<city>&count=1&language=en&format=json`
  - No match ⇒ response has **no `results` key** (not an empty list). Treat as "city not found".
- Forecast: `GET https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&current=...&daily=...&timezone=auto`
  - Errors return HTTP 400 with `{"error": true, "reason": "..."}`.
- No API key is required. Base URLs must still come from configuration so tests
  and alternative hosts can override them.
- Respect Open-Meteo's fair-use terms: never hammer the API, never retry in a tight loop.

## Architecture (layered — keep the boundaries)

```
src/weather_dashboard/
  config.py      # Settings model; load order: defaults < TOML file < env (WEATHER_*) < CLI flags
  errors.py      # Domain exception hierarchy (see below)
  models.py      # Pydantic models for raw API payloads + clean domain models
  http.py        # build_client(settings) -> httpx.Client; retry/backoff helper
  client.py      # OpenMeteoClient: geocode(), forecast(); ONLY place that does HTTP
  service.py     # Orchestration: city -> location -> forecast -> domain Dashboard object
  render.py      # rich rendering; pure function of domain objects, no I/O besides console
  cli.py         # typer app; maps domain errors to messages + exit codes
tests/
  fixtures/      # Recorded/hand-written JSON payloads (valid, partial, malformed)
  unit/          # models, config, retry logic, render
  integration/   # client + service with respx-mocked HTTP
```

Rules:

- **Only `client.py` touches `httpx`.** Higher layers see domain models and domain errors only.
- **Raw ≠ domain.** Parse raw JSON into `*Response` pydantic models, then map into
  domain dataclasses/models. Rendering never sees raw dicts.
- **Inject the `httpx.Client`** (or a transport) into `OpenMeteoClient` so tests can supply mocks.
- No global mutable state; no module-level network calls; no reading env vars outside `config.py`.

## Error handling policy

All failures surface as subclasses of `WeatherError` (in `errors.py`):

| Exception              | Raised when                                                     | CLI exit code |
| ---------------------- | --------------------------------------------------------------- | ------------- |
| `ConfigError`          | Invalid/missing config, bad TOML, out-of-range values           | 2             |
| `LocationNotFound`     | Geocoding returns no results                                    | 3             |
| `ApiTimeout`           | Connect/read timeout after retries exhausted                    | 4             |
| `ApiUnavailable`       | Network error, DNS failure, HTTP 5xx after retries, HTTP 429    | 4             |
| `ApiRequestError`      | HTTP 4xx (include Open-Meteo `reason` if present)               | 5             |
| `UnexpectedResponse`   | Non-JSON body, wrong content type, schema validation failure, missing/mismatched fields | 6 |

- Never let raw `httpx` or `pydantic.ValidationError` escape `client.py`; wrap them
  and chain with `raise ... from exc`.
- Retry **only** idempotent GETs, **only** on timeouts, connection errors, 429, 502/503/504.
  Exponential backoff with jitter, bounded by `max_retries` from config. Honour `Retry-After` when present (capped).
- Never retry on 4xx (other than 429) or on validation failures.
- Messages shown to users are short and actionable; full details go to the log (`--verbose`).
- Never log or print secrets (future-proofing even though Open-Meteo has none).

## Handling unexpected responses

Validate defensively; assume the API can change under us:

- Check status code, then `Content-Type`, then parse JSON, then validate schema.
- Arrays in the forecast payload (`daily.time`, `daily.temperature_2m_max`, …) must be
  equal length — raise `UnexpectedResponse` if not.
- Unknown extra fields are **ignored** (`model_config = ConfigDict(extra="ignore")`).
- Missing required fields ⇒ `UnexpectedResponse`. Nullable values (e.g. `null`
  precipitation) are allowed and rendered as `—`.
- Unknown WMO weather codes map to `"Unknown"`, never crash.

## Configuration

- Settings fields (minimum): `geocoding_base_url`, `forecast_base_url`,
  `connect_timeout`, `read_timeout`, `max_retries`, `backoff_base`, `units`
  (`metric`|`imperial`), `forecast_days` (1–16), `default_city`, `user_agent`.
- Precedence: built-in defaults < `config.toml` (path via `--config` or
  `$XDG_CONFIG_HOME/weather-dashboard/config.toml`) < env vars prefixed `WEATHER_` < CLI flags.
- Validate on load; invalid values raise `ConfigError` with the offending key named.
- Keep `config.example.toml` in the repo in sync with the Settings model.

## Testing rules

- **The test suite must never hit the real network.** Use `respx` to mock
  routes; configure respx with `assert_all_mocked=True` and `assert_all_called=True`.
- Store representative payloads in `tests/fixtures/*.json`; load via a fixture helper.
- Every error-table row above needs at least one test, including:
  timeout (`httpx.ConnectTimeout` / `ReadTimeout` side effects), connection error,
  500 → retry → success, 503 exhausted, 429 with `Retry-After`, 400 with `reason`,
  HTML/non-JSON body, empty body, missing field, mismatched array lengths,
  geocoding with no `results` key.
- Patch sleeping in retry tests (inject a `sleep` callable) — tests must be fast.
- Config tests use `monkeypatch` for env vars and `tmp_path` for TOML files.
- CLI tests use `typer.testing.CliRunner` and assert on exit codes + output.
- Optional live smoke test lives in `tests/live/`, marked `@pytest.mark.live`, and
  is **skipped by default** (`-m "not live"` in pytest config).

## Commands

```bash
uv sync                     # or: pip install -e ".[dev]"
uv run weather Berlin       # run the dashboard
uv run pytest               # all offline tests
uv run pytest -m live       # opt-in real API smoke test
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

Before declaring a task done: tests, ruff, and mypy must all pass.

## Working conventions

- Small, focused changes; one concern per commit. Conventional commit messages (`feat:`, `fix:`, `test:` …).
- Write or update tests in the same change as the code.
- Type-annotate everything; prefer dataclasses/pydantic models over dicts.
- Preserve existing comments and docstrings unrelated to your change.
- Update `README.md` and `config.example.toml` when behaviour or settings change.
- If a requirement is ambiguous, ask the user instead of guessing.

## Out of scope (unless the user asks)

Web/GUI frontends, databases, caching layers, multiple weather providers,
authentication, deployment, async rewrites.

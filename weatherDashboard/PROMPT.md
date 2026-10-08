# Build Prompt — Weather Dashboard

Copy everything below the line into your coding agent.

---

Build a **terminal Weather Dashboard** in this repository that consumes the public
**Open-Meteo** API (no API key). Read `AGENTS.md` first and follow it strictly — it
defines the stack, architecture, error policy, configuration rules, and testing rules.

## What the app does

```
weather <city> [--days N] [--units metric|imperial] [--config PATH] [--verbose]
```

1. Geocode the city via the Open-Meteo Geocoding API (first match).
2. Fetch the forecast for that lat/lon: current temperature, apparent temperature,
   humidity, wind speed, weather code; plus daily max/min temperature,
   precipitation probability, and weather code for `N` days.
3. Render with `rich`: a header panel (city, country, local time), a "current
   conditions" panel, and a daily forecast table. WMO weather codes map to
   human-readable descriptions (unknown codes → "Unknown").
4. If no city is given, use `default_city` from config; if none is configured,
   exit with a clear `ConfigError` message.

## Learning goals this build must demonstrate

1. **External API integration** — a single `OpenMeteoClient` with `geocode()` and
   `forecast()` methods; the only module that uses `httpx`.
2. **JSON** — raw payloads parsed into pydantic `*Response` models, then mapped
   to clean domain models used by the rest of the app.
3. **HTTP clients** — one reused `httpx.Client` with explicit connect/read
   timeouts, a `User-Agent` header, and base URLs from config; injected (not
   created inside methods) so it can be mocked.
4. **API failures/timeouts** — retry with exponential backoff + jitter only on
   timeouts, connection errors, 429, 502/503/504; honour `Retry-After`; never
   retry other 4xx. All failures become the domain exceptions in `AGENTS.md`
   with the documented CLI exit codes.
5. **Configuration management** — `pydantic-settings` with precedence
   defaults < TOML file < `WEATHER_*` env vars < CLI flags; validated on load;
   ship a `config.example.toml`.
6. **Handling unexpected responses** — check status → content type → JSON →
   schema; detect HTML/empty bodies, missing fields, mismatched daily array
   lengths, geocoding with no `results` key; ignore unknown extra fields;
   render `null` values as `—`.
7. **Mocking external APIs in tests** — `pytest` + `respx`, zero real network
   calls, JSON fixtures in `tests/fixtures/`, retry sleeps injected/patched so
   tests run fast. An optional live smoke test is marked `live` and skipped by default.

## Build in slices (stop and report after each)

1. **Scaffold** — `pyproject.toml` (src layout, `weather` console script, dev
   extras), ruff/mypy/pytest config, package skeleton, `errors.py`, README stub.
2. **Config** — Settings model, TOML + env + CLI precedence, validation,
   `config.example.toml`, unit tests for precedence and invalid values.
3. **Models** — raw response models + domain models + WMO code mapping; unit
   tests using fixture JSON (valid, partial/nullable, malformed).
4. **HTTP client + retries** — `build_client()`, retry helper with injectable
   sleep, `OpenMeteoClient`; respx tests covering every row of the error table.
5. **Service + rendering** — orchestration from city → `Dashboard`; `rich`
   rendering as a pure function; tests for service (mocked client) and render
   output snapshots.
6. **CLI** — typer app, error-to-exit-code mapping, `--verbose` logging; tests
   with `CliRunner` for success and each failure exit code.
7. **Polish** — README (setup, usage, config, architecture diagram, how mocking
   works), live smoke test, final pass of ruff + mypy + pytest.

## Required test cases (minimum)

- Happy path: geocode + forecast → rendered dashboard.
- City not found (no `results` key) → exit 3.
- Connect timeout and read timeout, retries exhausted → exit 4.
- 500 then 200 → succeeds after one retry (assert call count).
- 503 on every attempt → exit 4 after `max_retries + 1` calls.
- 429 with `Retry-After: 2` → sleep called with 2 (capped), then success.
- 400 with `{"error": true, "reason": "..."}` → exit 5, reason shown.
- HTML body / empty body / wrong content type → exit 6.
- Missing required field; mismatched daily array lengths → exit 6.
- Extra unknown fields ignored; `null` values rendered as `—`; unknown WMO code → "Unknown".
- Config: env overrides file, CLI overrides env, invalid `forecast_days=0` → exit 2.

## Definition of done

- `uv run pytest` passes with no network access (try it offline).
- `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src` are clean.
- `uv run weather Berlin` shows a working dashboard against the real API.
- README explains setup, usage, configuration precedence, error codes, and how the API is mocked in tests.

## Constraints

- Follow `AGENTS.md`; do not add dependencies beyond those listed without asking.
- Do not build a web UI, caching, a database, or multiple providers.
- If anything is ambiguous, ask before implementing.

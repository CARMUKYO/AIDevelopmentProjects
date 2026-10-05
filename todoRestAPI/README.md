# Todo REST API

A learning-focused Todo API built with Node, Express, TypeScript, SQLite
(`better-sqlite3`), Zod validation, and Vitest. See [PROJECT.md](PROJECT.md)
for the goals and decisions behind it, and
[docs/api-designs.md](docs/api-designs.md) for the design options considered.

## Setup

Requires Node 20+ and npm.

```sh
npm install
```

If npm reports blocked install scripts for `better-sqlite3` or `esbuild`,
approve and rebuild them once:

```sh
npm install-scripts approve better-sqlite3 esbuild
npm rebuild better-sqlite3 esbuild
```

## Scripts

| Command            | What it does                                    |
| ------------------ | ----------------------------------------------- |
| `npm run dev`      | Start the API with reload on `http://localhost:3000` |
| `npm run build`    | Compile TypeScript to `dist/`                   |
| `npm start`        | Run the compiled API                            |
| `npm run migrate`  | Apply pending SQL migrations                    |
| `npm test`         | Run unit + integration suites once              |
| `npm run test:watch` | Re-run suites on change                       |
| `npm run test:coverage` | Run suites with a coverage report          |

Configuration is via environment variables: `PORT` (default 3000),
`DB_PATH` (default `./data/todo.db`), `MIGRATIONS_DIR` (default
`./migrations`). The server runs migrations on boot, so `npm run dev`
works on a fresh checkout.

## API

Base path: `/api/v1/tasks`.

| Method | Path     | Status | Meaning                          |
| ------ | -------- | ------ | -------------------------------- |
| POST   | `/`      | 201    | Create a task                    |
| GET    | `/`      | 200    | List tasks, newest first         |
| GET    | `/:id`   | 200    | Get one task                     |
| PATCH  | `/:id`   | 200    | Partial update, incl. completion |
| PUT    | `/:id`   | 200    | Full replace of title/description|
| DELETE | `/:id`   | 204    | Delete a task                    |

List query parameters: `completed=true|false`, `limit` (default 20, max
100), `offset` (default 0). The list returns an envelope:

```json
{ "data": [ ... ], "limit": 20, "offset": 0, "total": 1 }
```

A task looks like this:

```json
{
  "id": 1,
  "title": "Buy milk",
  "description": "2% or oat",
  "completed": false,
  "created_at": "2026-10-05T06:53:24.993Z",
  "updated_at": "2026-10-05T06:53:24.993Z"
}
```

Rules: `title` is required (1–200 chars), `description` is optional
(max 2000, nullable), `completed` defaults to false, and completion
changes go through PATCH only — PUT rejects a `completed` key.

Errors share one shape:

```json
{ "error": { "code": "validation_error", "message": "...", "details": [ ... ] } }
```

Status codes: 200 reads/updates, 201 create (with a `Location` header),
204 delete, 400 validation or malformed JSON, 404 unknown task or
route, 500 unexpected errors.

Quick tour:

```sh
curl -X POST localhost:3000/api/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Buy milk"}'
curl 'localhost:3000/api/v1/tasks?completed=false&limit=10'
curl -X PATCH localhost:3000/api/v1/tasks/1 \
  -H 'Content-Type: application/json' \
  -d '{"completed":true}'
```

## Layout

- `src/server.ts` — boot: open DB, migrate, listen.
- `src/app.ts` — Express app factory (used by tests too).
- `src/routes/tasks.ts` — task endpoints.
- `src/schemas.ts` — Zod schemas and row-to-JSON mapping.
- `src/errors.ts` — `ApiError` plus 404/error middleware.
- `src/db/` — SQLite connection and migration runner.
- `migrations/` — numbered SQL migrations.
- `tests/unit/` — schema and migration tests.
- `tests/integration/` — supertest API tests per roadmap slice.

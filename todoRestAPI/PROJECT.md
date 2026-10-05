# Todo REST API — Project Record

Status: Draft

## Goals

- Learning project for building a Todo REST API with AI assistance.
- Practice: REST principles, HTTP methods/status codes, API design, database schema, CRUD, validation, exception handling, unit and integration testing.
- Support: create task, get task, list tasks, update task, delete task, mark task as completed.
- Use a database (choice still open).

## Non-goals (Accepted)

- Auth/users, frontend UI, deployment/hosting.
- Postgres migration (deferred later stage).
- Building Option B completion sub-resource (deferred alternative).

## Decisions

- D1 — Decision record location: `PROJECT.md` in repo root as the main grill record, plus a `docs/` folder for separate design/goal files. Source: user accepted either `PROJECT.md` or `AGENTS.md` and requested a `docs/` folder (2026-10-05 chat). Scope: documentation layout only, does not decide stack or API style.
- D2 — Backend stack: Node + Express. Source: user chose "the node one" (2026-10-05 chat). Scope: framework only; language variant, test runner, and database still open.
- D3 — Database: SQLite to start. Source: user chose "sqlite for now" (2026-10-05 chat). Scope: engine only; driver and data-access approach (raw SQL vs query layer) still open.
- D4 — Language variant: TypeScript. Source: user chose "typscript" [sic] (2026-10-05 chat). Scope: all Node + Express code.
- D5 — Data access: better-sqlite3 with plain SQL. Source: user chose "btter-sqlite3" [sic] (2026-10-05 chat). Scope: driver and query style only; migration approach still open.
- D6 — Migrations: tiny migration script with numbered SQL files from day one. Source: user chose "tiny migration" (2026-10-05 chat). Scope: schema evolution approach.
- D7 — Test runner: Vitest. Source: user chose "vitest" (2026-10-05 chat). Scope: runner only; unit vs integration split still open.
- D8 — API design: mix of Option A and Option C (pure REST with PATCH completion, plus /api/v1 versioning, filtering, and pagination). Source: user chose "mix a and c" (2026-10-05 chat). Scope: overall design direction; PUT vs PATCH, exact filters, and pagination params still open.
- D9 — Task fields and validation: id, title (required, 1–200 chars), description (optional, max 2000), completed (default false), created_at/updated_at; validated with Zod. Source: user chose "first one" (2026-10-05 chat). Scope: v1 task model and validation library.
- D10 — Error shape and status codes: single `{ error: { code, message, details? } }` shape; 200 reads/updates, 201 create, 204 delete, 400 validation, 404 unknown id, 500 unexpected via one Express error middleware. Source: user chose "one json shape" (2026-10-05 chat). Scope: v1 error policy.
- D11 — Updates: support both PUT (full replace) and PATCH (partial update). Source: user chose "support both" (2026-10-05 chat). Scope: update methods; whether completion is PATCH-only or also via PUT still open.
- D12 — List controls: `?completed` filter plus `?limit` (default 20, max 100) and `?offset` (default 0), newest first. Source: user chose "first one" (2026-10-05 chat). Scope: GET /api/v1/tasks v1 params.
- D13 — Tests: both unit (validation schemas, helpers) and integration (supertest against throwaway SQLite) from the start. Source: user chose "both from the start" (2026-10-05 chat). Scope: test layers; coverage target still open.
- D14 — Completion is PATCH-only; PUT rejects changes to completed. Source: user chose "first one" (2026-10-05 chat). Scope: update-method roles.

## Constraints

- Workspace started empty; no existing code or doc conventions.

## Risks

- Scope creep if auth, frontend, or deployment get added to a learning CRUD API.
- Choosing stack/DB before clarifying learning priorities could misalign effort.

## Validation (Accepted)

- Fresh checkout runs migrations, starts the API, and passes `npm test`.
- CRUD plus PATCH completion behave per D8/D11/D12; validation fails with 400 plus the D10 error shape; unknown ids 404.
- Unit and integration suites both present and passing under Vitest.

## Unresolved questions

- [x] Backend language/framework? → Node + Express (D2).
- [x] Database choice (SQLite vs Postgres vs other)? → SQLite to start (D3).
- [x] Language variant (TypeScript vs JavaScript)? → TypeScript (D4).
- [x] Data-access approach (raw SQL vs query layer)? → better-sqlite3 with plain SQL (D5).
- [x] Migration approach (migration script vs single schema file)? → tiny migration script (D6).
- [x] Test runner (Vitest vs Jest)? → Vitest (D7).
- [x] Test split (unit + integration vs integration-first)? → both from the start (D13).
- [x] Which API design option (see `docs/api-designs.md`)? → mix of A and C (D8).
- [x] PUT vs PATCH support (one or both)? → both (D11).
- [x] Completion via PUT allowed or PATCH-only? → PATCH-only (D14).
- [x] List filters and pagination params? → completed filter + limit/offset (D12).
- [x] Task fields and validation rules? → D9 fields with Zod (D9).
- [x] Error response shape and status code policy? → single error shape + status table (D10).
- [ ] Test scope (unit vs integration split, tooling)?

## Scope contract (Accepted)

Acceptance: user replied "accept" in chat on 2026-10-05.

- In scope: `PROJECT.md`, `docs/`, Node + Express + TypeScript source, numbered SQL migrations, Vitest unit + integration suites, package/config files.
- Out of scope: auth/users, frontend UI, deployment/hosting, Postgres migration, Option B build.
- Done means: fresh checkout migrates, starts the API, and passes tests; validation and error behavior demonstrated per D9/D10.
- Later stages are deferred proposals; accepting this record never approves them.
- Words like go/do it all authorize only the accepted boundary.

## Build progress

- Roadmap 1 slices 1–5 implemented on 2026-10-05: scaffold + POST/GET,
  GET-by-id + DELETE, PATCH + PUT, list filter/pagination/envelope,
  hardening + README. Full Vitest suite green, typecheck clean.

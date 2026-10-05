# Todo API — Design Options

Status: Draft

This file will hold the multiple API designs for comparison. Details stay
deferred until stack and database are chosen. No option is approved yet.

## Shared assumptions (proposed)

- Resource: `Task` with id, title, optional description, completed flag, timestamps.
- JSON request/response bodies.
- Standard CRUD plus a way to mark a task completed/uncompleted.
- Consistent error shape and status codes (policy TBD).

## Option A — Pure REST with PATCH for completion (proposed)

- POST /tasks — create.
- GET /tasks — list (filtering/pagination TBD).
- GET /tasks/{id} — get one.
- PUT /tasks/{id} — full replace; PATCH /tasks/{id} — partial update.
- PATCH /tasks/{id} with completed true/false — mark completed/uncompleted.
- DELETE /tasks/{id} — delete.
- Strengths: smallest surface, most REST-pure, teaches PUT vs PATCH and status codes.
- Tradeoffs: completion is less discoverable than a named action.

## Option B — REST plus completion sub-resource (proposed)

- Same CRUD as Option A, but completion is explicit:
- POST /tasks/{id}/complete — mark completed.
- DELETE /tasks/{id}/complete — mark uncompleted (or POST .../uncomplete).
- Strengths: explicit and discoverable action, good discussion of sub-resources vs RPC.
- Tradeoffs: slightly larger surface, two ways to change the same field unless PATCH is restricted.

## Option C — Versioned API with filtering and pagination (proposed)

- Same as A or B, but under /api/v1 and with list controls:
- GET /api/v1/tasks?completed=true&limit=20&offset=0 — filtered, paginated list.
- Strengths: closest to production practice, teaches versioning and collection design.
- Tradeoffs: more to build and test for a first learning pass.

## Chosen direction (Draft)

- Build a mix of Option A and Option C: pure REST CRUD with PATCH completion under /api/v1, plus list filtering and pagination. Source: user chose "mix a and c" (2026-10-05 chat). Option B stays documented as a deferred alternative.

## Unresolved

- [x] Which option to build first? → mix of A and C.
- [ ] PUT vs PATCH support (one or both)?
- [ ] List filtering, sorting, pagination requirements?
- [ ] Version prefix (/api/v1) yes or no?

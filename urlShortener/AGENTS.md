# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project

A URL shortener service: converts long URLs into short codes, redirects, supports expiration,
records basic statistics, and validates input. The full task brief lives in
[`PROMPT.md`](./PROMPT.md). Design and risk docs live in `docs/`.

This is a **learning project**. Explain trade-offs, don't just pick an answer.

## Workflow Rules

1. **Design before code.** Do not write implementation code until `docs/DESIGN.md` exists and
   has been approved by the user.
2. **Always ask "What could go wrong?"** Before finishing any non-trivial change (schema,
   ID generation, redirect path, caching, auth, validation), add a short
   *What could go wrong* note to your response, and record significant risks in `docs/RISKS.md`.
3. **Stop at phase boundaries** defined in `PROMPT.md` and wait for the user's review.
4. **Keep docs in sync.** If the implementation diverges from `docs/DESIGN.md`, update the doc
   in the same change.
5. **Ask, don't assume,** when a requirement is ambiguous (e.g. dedupe behavior, 301 vs 302,
   whether auth is in scope).

## Engineering Rules

### Database
- All schema changes go through migrations; never edit an applied migration.
- Enforce uniqueness of short codes with a DB **unique constraint**, not only application logic.
- Store timestamps in UTC.
- Do not do a synchronous `UPDATE ... SET clicks = clicks + 1` on the redirect hot path
  without justifying it in the design doc (row contention).

### Identifiers
- Short codes must not be trivially enumerable unless the design doc explicitly accepts that risk.
- Custom aliases and generated codes share one namespace; reserved words
  (`api`, `health`, `stats`, `admin`, `static`, etc.) must be blocked.
- Collision handling must be deterministic and tested.

### API
- Versioned under `/api/v1`. Consistent JSON error shape, e.g.
  `{ "error": { "code": "INVALID_URL", "message": "..." } }`.
- Use correct status codes: `201` create, `400/422` validation, `404` unknown,
  `409` alias conflict, `410` expired, `429` rate limited.

### Security
- Allow only `http` and `https` schemes. Reject `javascript:`, `data:`, `file:`, etc.
- Reject URLs pointing at the shortener's own domain (redirect loops).
- Cap input sizes (URL length, alias length/charset).
- Rate-limit the create endpoint.
- Never store raw client IPs for statistics; hash or truncate if needed.
- No secrets in code or commits; use env vars and keep `.env.example` updated.

### Performance
- The redirect path is the hot path: minimize DB round-trips, prefer cache-aside reads,
  and record clicks asynchronously or in batches.
- Cache entries must respect link expiration (TTL ≤ time until `expires_at`).

## Testing

- Every edge case listed in `PROMPT.md` needs an automated test.
- Run the full test suite before declaring a task complete, and report the result.
- Tests must not depend on wall-clock time — inject a clock for expiration logic.

## Response Format for Each Task

End each substantive response with:

```
### What could go wrong?
- <risk 1> → <mitigation or "accepted because ...">
- <risk 2> → ...
```

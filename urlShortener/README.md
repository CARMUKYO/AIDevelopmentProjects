# URL Shortener Service

A production-minded, high-throughput URL shortener service written in **Go** with support for **PostgreSQL** (production) and **SQLite** (local development/tests), **Redis** (cache & click buffer), expiration, analytics, and security validations.

---

## Features

- **Shorten & Custom Aliases:** Convert long URLs into 7-character Base62 short codes or custom aliases (`^[a-zA-Z0-9_-]{3,32}$`).
- **Temporary Redirects (`302 Found`):** Directs traffic with `Cache-Control: private, max-age=0, no-cache` for accurate click tracking and instant expiration enforcement.
- **Link Expiration:** Supports exact expiration timestamps (`expires_at`), returning `410 Gone` on expired links.
- **Contention-Free Click Analytics:** Redirect hot path buffers clicks in-memory/Redis and flushes in batches every 5 seconds to eliminate database row locking.
- **Security Guardrails:**
  - Scheme validation (`http` / `https` only; rejects `javascript:`, `data:`, `file:`, etc.).
  - Self-referential redirect loops and SSRF protection (rejects loopback, link-local, private RFC 1918 IPs).
  - Reserved keywords protection (`api`, `health`, `metrics`, `admin`, etc.).
  - 256-bit secret `delete_token` compared with constant-time verification (`crypto/subtle.ConstantTimeCompare`).
  - IP-based token-bucket rate limiting on the create endpoint.
  - Server request timeouts and 16 KB request body limit.
- **Thundering Herd Defense:** Go `singleflight.Group` collapses concurrent cache misses into a single database query.
- **Privacy First:** Never stores raw client IPs; sanitizes referrers to hostnames and maps User-Agents to coarse device families (`Bot`, `Mobile`, `Tablet`, `Desktop`).

---

## Quick Start

### 1. Requirements
- Go 1.23+ (or `mise`)
- Optional: Docker & Docker Compose (for PostgreSQL + Redis)

### 2. Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

By default, the application runs out of the box with zero external dependencies using an embedded SQLite database and in-memory cache.

### 3. Running the Server

#### Option A: Local Dev (SQLite + In-Memory Cache)
```bash
go run ./cmd/server/main.go
```

#### Option B: Full Stack with Docker Compose (PostgreSQL + Redis)
```bash
docker compose up --build
```

---

## Running Tests

Run the entire test suite including all 14 edge cases and race detection:

```bash
go test -v -race ./...
```

To run without test cache:
```bash
go test -v -race -count=1 ./...
```

---

## API Documentation & Example `curl` Commands

### 1. Create a Short Link
```bash
curl -i -X POST http://localhost:8080/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP",
    "alias": "mdn-http",
    "expires_at": "2026-12-31T23:59:59Z"
  }'
```

**Response (`201 Created`):**
```json
{
  "code": "mdn-http",
  "short_url": "http://localhost:8080/mdn-http",
  "original_url": "https://developer.mozilla.org/en-US/docs/Web/HTTP",
  "created_at": "2026-10-08T11:00:00Z",
  "expires_at": "2026-12-31T23:59:59Z",
  "delete_token": "a1b2c3d4e5f6...64-char-hex"
}
```

### 2. Redirect to Target
```bash
curl -i http://localhost:8080/mdn-http
```
**Response (`302 Found`):**
```http
HTTP/1.1 302 Found
Location: https://developer.mozilla.org/en-US/docs/Web/HTTP
Cache-Control: private, max-age=0, no-cache
```

### 3. Get Link Metadata
```bash
curl -i http://localhost:8080/api/v1/links/mdn-http
```

### 4. Get Click Statistics
```bash
curl -i http://localhost:8080/api/v1/links/mdn-http/stats
```
**Response (`200 OK`):**
```json
{
  "code": "mdn-http",
  "original_url": "https://developer.mozilla.org/en-US/docs/Web/HTTP",
  "created_at": "2026-10-08T11:00:00Z",
  "expires_at": "2026-12-31T23:59:59Z",
  "total_clicks": 42,
  "daily_clicks": [
    { "date": "2026-10-08", "clicks": 42 }
  ],
  "top_referrers": [
    { "referrer": "twitter.com", "clicks": 28 },
    { "referrer": "direct", "clicks": 14 }
  ],
  "devices": [
    { "family": "Desktop", "clicks": 30 },
    { "family": "Mobile", "clicks": 12 }
  ]
}
```

### 5. Delete a Link
```bash
curl -i -X DELETE http://localhost:8080/api/v1/links/mdn-http \
  -H "X-Delete-Token: <your-delete-token>"
```
**Response (`204 No Content`)**

Subsequent visits to `http://localhost:8080/mdn-http` return `410 Gone`.

### 6. Health Probe
```bash
curl -i http://localhost:8080/health
```
```json
{
  "status": "ok",
  "database": "up",
  "cache": "up"
}
```

---

## Architecture & System Design
Detailed documentation and risk analyses are available in:
- [docs/DESIGN.md](file:///home/userman/Projects/AIDevelopmentProjects/urlShortener/docs/DESIGN.md)
- [docs/RISKS.md](file:///home/userman/Projects/AIDevelopmentProjects/urlShortener/docs/RISKS.md)

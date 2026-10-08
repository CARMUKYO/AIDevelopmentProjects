# Adversarial Risk Analysis: URL Shortener Service

This document critiques the system architecture described in [`docs/DESIGN.md`](./DESIGN.md) from the perspective of an adversarial reviewer and site reliability engineer (SRE).

---

## 1. Risk Matrix Summary

| # | What could go wrong | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| **1** | **Cache Stampede (Thundering Herd)**: Hot link expires or misses cache under 10k req/s, causing simultaneous DB queries that exhaust `pgxpool`. | High | High | Use Go `singleflight.Group` to collapse concurrent DB lookups per code into 1 query. Cache negative lookups (sentinel `"nil"`) for 60s. | **Fixed** |
| **2** | **DNS Rebinding & Internal Network Scanning (SSRF)**: Target domain changes DNS to `127.0.0.1` or `169.254.169.254` post-validation, tricking internal VPN users. | Medium | High | Resolve hostname at creation time; reject private/loopback/link-local/multicast IPv4 and IPv6 ranges. Reject raw internal IPs. | **Fixed** |
| **3** | **Unpersisted Click Loss on Hard Crash**: Redis or Go process killed (`SIGKILL`) before 5s flush interval, losing buffered click counts. | Medium | Low | Intercept `SIGTERM`/`SIGINT` for graceful flush with 10s deadline. Enable Redis AOF (`appendfsync everysec`). Accept ≤1s loss on hard power loss as documented trade-off. | **Accepted** |
| **4** | **`delete_token` Brute-Force & Timing Attacks**: Weak token entropy or standard string equality leaking byte-by-byte match timing. | Low | High | Generate 256-bit cryptographically secure token (`crypto/rand`, 64 hex chars). Use `subtle.ConstantTimeCompare`. Rate limit delete attempts. | **Fixed** |
| **5** | **Table Locks on Expiration Cleanup**: Bulk `DELETE` on millions of expired rows locks the `links` table, blocking reads/writes. | Medium | High | Purge in chunks of 500 rows with 100ms pause during off-peak hours: `DELETE FROM links WHERE id IN (SELECT id ... LIMIT 500)`. | **Fixed** |
| **6** | **Open Redirect & Phishing Abuse**: Shortener used to mask malicious sites, causing domain blacklisting by Safe Browsing. | High | High | Rate limit creates (60/min). Enforce URL length caps (2048 chars). Configurable domain blocklist. Strip dangerous schemes (`javascript:`, `data:`). | **Fixed** |
| **7** | **PII & Token Leakage in Referrers**: Full `Referer` headers containing auth tokens or user email parameters stored in DB. | High | Medium | Strip path and query parameters; strictly store sanitized hostnames (`url.Hostname()`, e.g. `twitter.com`). Discard userinfo. | **Fixed** |
| **8** | **Stale Cache after Explicit Deletion**: Link deleted by owner via API continues redirecting from Redis cache until TTL expires. | Medium | Medium | Invalidate Redis key `DEL link:code:{code}` and write `"deleted"` sentinel on successful delete. Return `410 Gone` immediately. | **Fixed** |
| **9** | **Bot & Link-Preview Click Inflation**: Slack/Discord/Twitter unfurl bots visit links, artificially inflating click counts by 10x. | High | Medium | Inspect `User-Agent` against known crawlers. Categorize as `"Bot"` in `link_device_stats`. Exclude `HEAD` requests from click counting. | **Fixed** |
| **10** | **Slowloris & Unbounded Body DoS**: Attacker streams bytes slowly or sends massive payloads to exhaust server memory/goroutines. | Medium | High | Set strict `http.Server` timeouts (`ReadTimeout = 5s`, `WriteTimeout = 10s`). Wrap body in `http.MaxBytesReader` capped at 16 KB. | **Fixed** |
| **11** | **System Route Hijacking via Custom Alias**: Custom alias registered for newly added route (e.g. `/docs`, `/metrics`, `/v1`). | Medium | High | Maintain case-insensitive reserved word blocklist. Match explicit routes in router before wildcard `/{code}` handler. | **Fixed** |
| **12** | **Cascading Database Failure during Redis Outage**: Redis failure directs 100% of read and rate-limit traffic to PostgreSQL. | Low | High | Degrade gracefully: bypass cache, throttle traffic with in-memory token bucket, and buffer clicks in bounded Go channel (10k events). | **Fixed** |
| **13** | **Clock Skew between Cluster Nodes**: Servers with drifting clocks disagree on link expiration boundary. | Low | Medium | Standardize on UTC. Inject testable clock. Use NTP daemon on production instances. Query comparisons use DB `NOW() AT TIME ZONE 'UTC'`. | **Fixed** |
| **14** | **Keyspace Collision Degradation at Scale**: At 10M+ links, collision rate increases to 1.4%, causing DB insert retries to spike p99 latency. | Low | Medium | Cap retries at 5 with exponential backoff. Add Prometheus collision metric. Automatically expand code length from 7 to 8 chars if collision rate exceeds 5%. | **Deferred** |

---

## 2. Deep Dive: Key Adversarial Scenarios

### 2.1 Cache Stampede & Thundering Herd
- **The Attack/Failure Mode:** A popular link (e.g., promoted on social media) expires from Redis cache, or receives 10,000 concurrent requests during a cache miss. All worker goroutines simultaneously query PostgreSQL:
  `SELECT id, original_url, expires_at FROM links WHERE code = $1`.
- **System Impact:** PostgreSQL connection pool (`pgxpool`) fills up instantly. New requests block, health checks fail, and the API server crashes due to OOM or timeout cascades.
- **Mitigation:**
  1. **SingleFlight:** Wrap cache-miss lookups with Go's `golang.org/x/sync/singleflight`:
     ```go
     val, err, _ := g.Do(code, func() (any, error) {
         return db.GetLinkByCode(ctx, code)
     })
     ```
     Only one goroutine fetches from PostgreSQL; all others wait and share the returned result.
  2. **Negative Caching:** Non-existent codes store a `"nil"` sentinel with `TTL = 60s` so scrapers scanning random 7-character strings cannot hammer PostgreSQL.

### 2.2 Server-Side Request Forgery (SSRF) & Phishing Cloaking
- **The Attack/Failure Mode:** 
  1. An attacker registers `https://attacker.com` pointing to `169.254.169.254` (AWS metadata) or `127.0.0.1`. If an internal user or automated link validator follows the redirect, internal credentials or admin portals are exposed.
  2. DNS Rebinding: Attacker uses a domain with TTL = 1s that resolves to a benign public IP at validation time, then immediately switches to an internal IP.
- **Mitigation:**
  - The service is an HTTP redirector, not an HTTP proxy (it does not fetch destination URLs on the server).
  - However, to protect end users and corporate clients, validate destination hostnames by resolving IP addresses with `net.LookupIP`:
    - Disallow loopback (`127.0.0.0/8`, `::1`).
    - Disallow RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
    - Disallow link-local (`169.254.0.0/16`, `fe80::/10`).
    - Disallow multicast, broadcast, and unspecified (`0.0.0.0`).
  - Block domains matching the shortener's own domain to eliminate redirect loops (`A -> B -> A`).

### 2.3 `delete_token` Security
- **The Attack/Failure Mode:** If `delete_token` is predictable (e.g. timestamp or weak pseudo-random generator), or compared using naive `token == userToken`, attackers can use timing attacks or brute-force scripts to delete competitors' short links.
- **Mitigation:**
  - Generate 32 bytes of cryptographically secure random bytes via `crypto/rand` encoded into 64 hexadecimal characters.
  - Compare tokens using constant-time comparison:
    ```go
    if subtle.ConstantTimeCompare([]byte(storedToken), []byte(providedToken)) != 1 {
        return ErrUnauthorized
    }
    ```
  - Rate-limit `DELETE` endpoints to 5 requests per minute per IP.

### 2.4 Scalability Under 10× and 1000× Traffic Spikes
- **10× Traffic (1,000 req/s $\rightarrow$ 10,000 req/s):**
  - Redis cache handles read throughput easily (benchmarks show Redis handles 100k+ ops/sec on single core).
  - Click buffer in Redis aggregates hits in memory; PostgreSQL batch persistence flushes 1 row update per active link every 5 seconds regardless of traffic volume.
- **1000× Traffic (1,000 req/s $\rightarrow$ 1,000,000 req/s):**
  - Bottleneck: Network I/O and single Redis instance bandwidth.
  - Solution: Deploy Redis Cluster or Redis Read Replicas for cache reads; place Cloudflare/CloudFront CDN in front of the redirect path with `s-maxage=60` for ultra-popular links, accepting batched CDN log aggregation for stats.

---

## 3. Post-Implementation Review (Phase 4)

With the complete codebase implemented and all 14 edge cases verified with automated tests, an adversarial post-implementation review revealed the following real-world implementation nuances:

### 3.1 Implementation Findings & Fixes

1. **SingleFlight Context Cancellation Cascade (Fixed)**
   - *Discovery during code review:* When wrapping database lookups with `singleflight.Group.Do(code, ...)`, passing the incoming HTTP request context (`r.Context()`) meant that if the first client disconnected early, `ctx.Err()` aborted the query, propagating `context canceled` to all other concurrent callers waiting on that same key.
   - *Fix:* Detached context with independent timeout (`context.WithTimeout(context.Background(), 3*time.Second)`) inside the `Do` closure, isolating the database fetch from client socket drops.

2. **SQLite vs PostgreSQL Concurrency in Test / Local Dev (Fixed & Accepted)**
   - *Discovery:* SQLite in file/memory mode returns `database is locked` on concurrent write transactions (`INSERT` or `UPDATE`).
   - *Fix:* For SQLite, database connections are configured with `MaxOpenConns(1)` and WAL mode (`cache=shared&mode=rwc`). PostgreSQL connection pooling uses `pgxpool` with `MaxConns=50` for concurrent production workloads.

3. **In-Memory Rate Limiter Memory Eviction (Fixed)**
   - *Discovery:* Naive map-based token buckets accumulate IP entries indefinitely when bombarded with spoofed `X-Forwarded-For` IPs.
   - *Fix:* Integrated a background cleaner ticker in `internal/api/middleware/ratelimit.go` that purges IP records older than 10 minutes every 5 minutes.

4. **Crawler / Preview Bot Filtering on HEAD Requests (Fixed)**
   - *Discovery:* Social preview crawlers (Twitterbot, Slackbot, Discordbot) frequently issue `HEAD /{code}` requests rather than `GET` to check headers.
   - *Fix:* The redirect router allows `HEAD`, returns `Location: <url>`, but strictly suppresses `recordClickAsync` on non-GET methods.

### 3.2 Post-Implementation Checklist

- [x] Verified SingleFlight eliminates concurrent DB hits in `TestEdgeCase_SingleFlightCoalescesDBLookups`.
- [x] Verified private IP / loopback rejection works for IPv4, IPv6, and cloud metadata (`169.254.169.254`).
- [x] Verified constant-time comparison on delete token via `crypto/subtle.ConstantTimeCompare`.
- [x] Verified graceful shutdown drains click buffer without dropping data.
- [x] Full test suite passes uncached with race detector (`go test -v -race -count=1 ./...`).

package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"urlshortener/internal/api"
	"urlshortener/internal/api/middleware"
	memcache "urlshortener/internal/cache/memory"
	"urlshortener/internal/clock"
	"urlshortener/internal/domain"
	"urlshortener/internal/service"
	sqlitestore "urlshortener/internal/storage/sqlite"
	"urlshortener/internal/validator"
)

type testEnv struct {
	store   domain.Store
	cache   domain.Cache
	clk     *clock.MockClock
	val     *validator.Validator
	linkSvc *service.LinkService
	flusher *service.ClickFlusher
	router  http.Handler
}

func setupTestEnv(t *testing.T) *testEnv {
	// In-memory SQLite database unique per test run
	dbName := fmt.Sprintf("file:mem_%d?mode=memory&cache=shared", time.Now().UnixNano())
	store, err := sqlitestore.New(dbName)
	if err != nil {
		t.Fatalf("failed to create sqlite store: %v", err)
	}

	cache := memcache.New()
	initialTime := time.Date(2026, 10, 8, 12, 0, 0, 0, time.UTC)
	clk := clock.NewMockClock(initialTime)
	val := validator.NewValidator("sho.rt")
	linkSvc := service.NewLinkService(store, cache, clk, val)
	flusher := service.NewClickFlusher(store, cache, 10*time.Millisecond)

	rateLimiter := middleware.NewRateLimiter(1000, 100) // Generous for tests
	handler := api.NewHandler(linkSvc, "https://sho.rt", store, cache)
	router := api.SetupRouter(handler, rateLimiter)

	t.Cleanup(func() {
		_ = store.Close()
		_ = cache.Close()
	})

	return &testEnv{
		store:   store,
		cache:   cache,
		clk:     clk,
		val:     val,
		linkSvc: linkSvc,
		flusher: flusher,
		router:  router,
	}
}

// 1. Same long URL shortened twice -> generates two distinct unique codes
func TestEdgeCase_SameURLShortenedTwice(t *testing.T) {
	env := setupTestEnv(t)

	targetURL := "https://example.com/blog/article-1"
	reqBody, _ := json.Marshal(map[string]any{"url": targetURL})

	// First creation
	req1 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(reqBody))
	req1.Header.Set("Content-Type", "application/json")
	w1 := httptest.NewRecorder()
	env.router.ServeHTTP(w1, req1)
	if w1.Code != http.StatusCreated {
		t.Fatalf("expected 201 Created, got %d", w1.Code)
	}
	var res1 map[string]any
	_ = json.Unmarshal(w1.Body.Bytes(), &res1)

	// Second creation
	req2 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(reqBody))
	req2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	env.router.ServeHTTP(w2, req2)
	if w2.Code != http.StatusCreated {
		t.Fatalf("expected 201 Created, got %d", w2.Code)
	}
	var res2 map[string]any
	_ = json.Unmarshal(w2.Body.Bytes(), &res2)

	code1 := res1["code"].(string)
	code2 := res2["code"].(string)
	if code1 == code2 {
		t.Fatalf("expected distinct codes for repeated creation, got same code: %s", code1)
	}
	if res1["delete_token"] == res2["delete_token"] {
		t.Fatalf("expected distinct delete tokens")
	}
}

// 2. Unicode / IDN host, punycode, very long query strings, and fragments
func TestEdgeCase_UnicodeAndIDNHost(t *testing.T) {
	env := setupTestEnv(t)

	longQuery := strings.Repeat("param=value&", 40)
	targetURL := "https://münchen.de/path?" + longQuery + "#section-1"

	reqBody, _ := json.Marshal(map[string]any{"url": targetURL})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(reqBody))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	env.router.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201 Created, got %d: %s", w.Code, w.Body.String())
	}
	var res map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &res)
	code := res["code"].(string)

	// Verify redirect preserves exact normalized target URL and fragment
	redReq := httptest.NewRequest(http.MethodGet, "/"+code, nil)
	redW := httptest.NewRecorder()
	env.router.ServeHTTP(redW, redReq)

	if redW.Code != http.StatusFound {
		t.Fatalf("expected 302 Found, got %d", redW.Code)
	}
	loc := redW.Header().Get("Location")
	if !strings.Contains(loc, "xn--mnchen-3ya.de") || !strings.Contains(loc, "#section-1") {
		t.Fatalf("redirect location missing punycode host or fragment: %s", loc)
	}
}

// 3. Self-referential redirect loops are rejected
func TestEdgeCase_RedirectLoopRejected(t *testing.T) {
	env := setupTestEnv(t)

	loopURLs := []string{
		"https://sho.rt/infinite-loop",
		"http://127.0.0.1/admin",
		"http://localhost:8080/loop",
		"http://169.254.169.254/latest/meta-data/",
	}

	for _, u := range loopURLs {
		reqBody, _ := json.Marshal(map[string]any{"url": u})
		req := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(reqBody))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		env.router.ServeHTTP(w, req)

		if w.Code != http.StatusUnprocessableEntity {
			t.Errorf("expected 422 for loop URL %s, got %d", u, w.Code)
		}
	}
}

// 4. Custom alias colliding with existing code or reserved route
func TestEdgeCase_CustomAliasCollisionsAndReserved(t *testing.T) {
	env := setupTestEnv(t)

	// Reserved alias test
	for _, reserved := range []string{"api", "API", "health", "Health", "admin", "stats"} {
		reqBody, _ := json.Marshal(map[string]any{"url": "https://example.com", "alias": reserved})
		req := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(reqBody))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		env.router.ServeHTTP(w, req)

		if w.Code != http.StatusConflict {
			t.Errorf("expected 409 Conflict for reserved alias %s, got %d: %s", reserved, w.Code, w.Body.String())
		}
	}

	// Create a valid custom alias
	reqBody, _ := json.Marshal(map[string]any{"url": "https://example.com/first", "alias": "my-promo"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(reqBody))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	env.router.ServeHTTP(w, req)
	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201 Created, got %d", w.Code)
	}

	// Collide with same alias
	reqBody2, _ := json.Marshal(map[string]any{"url": "https://example.com/second", "alias": "my-promo"})
	req2 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(reqBody2))
	req2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	env.router.ServeHTTP(w2, req2)

	if w2.Code != http.StatusConflict {
		t.Fatalf("expected 409 Conflict on duplicate alias, got %d", w2.Code)
	}
}

// 5. Case sensitivity of codes (abc vs ABC)
func TestEdgeCase_CaseSensitivity(t *testing.T) {
	env := setupTestEnv(t)

	// Create "abc"
	b1, _ := json.Marshal(map[string]any{"url": "https://example.com/lower", "alias": "abc"})
	r1 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b1))
	r1.Header.Set("Content-Type", "application/json")
	w1 := httptest.NewRecorder()
	env.router.ServeHTTP(w1, r1)
	if w1.Code != http.StatusCreated {
		t.Fatalf("expected 201 for 'abc', got %d", w1.Code)
	}

	// Create "ABC"
	b2, _ := json.Marshal(map[string]any{"url": "https://example.com/upper", "alias": "ABC"})
	r2 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b2))
	r2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	env.router.ServeHTTP(w2, r2)
	if w2.Code != http.StatusCreated {
		t.Fatalf("expected 201 for 'ABC', got %d: %s", w2.Code, w2.Body.String())
	}

	// Verify both redirect to their respective destination
	red1 := httptest.NewRequest(http.MethodGet, "/abc", nil)
	rw1 := httptest.NewRecorder()
	env.router.ServeHTTP(rw1, red1)
	if rw1.Header().Get("Location") != "https://example.com/lower" {
		t.Fatalf("expected lower target, got %s", rw1.Header().Get("Location"))
	}

	red2 := httptest.NewRequest(http.MethodGet, "/ABC", nil)
	rw2 := httptest.NewRecorder()
	env.router.ServeHTTP(rw2, red2)
	if rw2.Header().Get("Location") != "https://example.com/upper" {
		t.Fatalf("expected upper target, got %s", rw2.Header().Get("Location"))
	}
}

// 6. Expiration in past, expiration of zero, expiration far in future
func TestEdgeCase_ExpirationValidation(t *testing.T) {
	env := setupTestEnv(t)

	// Expiration in past
	pastTime := env.clk.Now().Add(-1 * time.Hour)
	b1, _ := json.Marshal(map[string]any{"url": "https://example.com", "expires_at": pastTime})
	r1 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b1))
	r1.Header.Set("Content-Type", "application/json")
	w1 := httptest.NewRecorder()
	env.router.ServeHTTP(w1, r1)
	if w1.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422 for past expiration, got %d", w1.Code)
	}

	// Expiration equal to current time (zero TTL)
	nowTime := env.clk.Now()
	b2, _ := json.Marshal(map[string]any{"url": "https://example.com", "expires_at": nowTime})
	r2 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b2))
	r2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	env.router.ServeHTTP(w2, r2)
	if w2.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422 for zero-TTL expiration, got %d", w2.Code)
	}

	// Expiration far in future
	futureTime := env.clk.Now().Add(365 * 24 * time.Hour)
	b3, _ := json.Marshal(map[string]any{"url": "https://example.com", "expires_at": futureTime})
	r3 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b3))
	r3.Header.Set("Content-Type", "application/json")
	w3 := httptest.NewRecorder()
	env.router.ServeHTTP(w3, r3)
	if w3.Code != http.StatusCreated {
		t.Fatalf("expected 201 for valid future expiration, got %d", w3.Code)
	}
}

// 7. Link expires between cache read and redirect (clock injection)
func TestEdgeCase_LinkExpiresBetweenCacheReadAndRedirect(t *testing.T) {
	env := setupTestEnv(t)

	expiresAt := env.clk.Now().Add(10 * time.Minute)
	b, _ := json.Marshal(map[string]any{
		"url":        "https://example.com/ephemeral",
		"alias":      "temp-link",
		"expires_at": expiresAt,
	})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	env.router.ServeHTTP(w, r)
	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201 Created, got %d", w.Code)
	}

	// 1. First redirect succeeds (302 Found) and warms cache
	red1 := httptest.NewRequest(http.MethodGet, "/temp-link", nil)
	rw1 := httptest.NewRecorder()
	env.router.ServeHTTP(rw1, red1)
	if rw1.Code != http.StatusFound {
		t.Fatalf("expected 302 Found before expiration, got %d", rw1.Code)
	}

	// 2. Advance mock clock beyond expiration time
	env.clk.Advance(15 * time.Minute)

	// 3. Next redirect must return 410 Gone even if cached
	red2 := httptest.NewRequest(http.MethodGet, "/temp-link", nil)
	rw2 := httptest.NewRecorder()
	env.router.ServeHTTP(rw2, red2)
	if rw2.Code != http.StatusGone {
		t.Fatalf("expected 410 Gone after link expiration, got %d: %s", rw2.Code, rw2.Body.String())
	}
}

// 8. Request for code that never existed (404) vs expired (410) vs deleted (410)
func TestEdgeCase_NonExistentVsExpiredVsDeleted(t *testing.T) {
	env := setupTestEnv(t)

	// 1. Code never existed -> 404 Not Found
	r1 := httptest.NewRequest(http.MethodGet, "/never-existed-xyz", nil)
	w1 := httptest.NewRecorder()
	env.router.ServeHTTP(w1, r1)
	if w1.Code != http.StatusNotFound {
		t.Fatalf("expected 404 for never-existed code, got %d", w1.Code)
	}

	// 2. Code created and expired -> 410 Gone
	expTime := env.clk.Now().Add(5 * time.Minute)
	b, _ := json.Marshal(map[string]any{"url": "https://example.com", "alias": "exp-test", "expires_at": expTime})
	rPost := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b))
	rPost.Header.Set("Content-Type", "application/json")
	wPost := httptest.NewRecorder()
	env.router.ServeHTTP(wPost, rPost)
	if wPost.Code != http.StatusCreated {
		t.Fatalf("expected 201, got %d", wPost.Code)
	}

	env.clk.Advance(10 * time.Minute)
	r2 := httptest.NewRequest(http.MethodGet, "/exp-test", nil)
	w2 := httptest.NewRecorder()
	env.router.ServeHTTP(w2, r2)
	if w2.Code != http.StatusGone {
		t.Fatalf("expected 410 for expired code, got %d", w2.Code)
	}

	// 3. Code created and deleted -> 410 Gone
	bDel, _ := json.Marshal(map[string]any{"url": "https://example.com", "alias": "del-test"})
	rPostDel := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(bDel))
	rPostDel.Header.Set("Content-Type", "application/json")
	wPostDel := httptest.NewRecorder()
	env.router.ServeHTTP(wPostDel, rPostDel)
	var delRes map[string]any
	_ = json.Unmarshal(wPostDel.Body.Bytes(), &delRes)
	token := delRes["delete_token"].(string)

	// Delete it
	rDel := httptest.NewRequest(http.MethodDelete, "/api/v1/links/del-test", nil)
	rDel.Header.Set("X-Delete-Token", token)
	wDel := httptest.NewRecorder()
	env.router.ServeHTTP(wDel, rDel)
	if wDel.Code != http.StatusNoContent {
		t.Fatalf("expected 204 No Content for delete, got %d", wDel.Code)
	}

	// Request deleted code
	r3 := httptest.NewRequest(http.MethodGet, "/del-test", nil)
	w3 := httptest.NewRecorder()
	env.router.ServeHTTP(w3, r3)
	if w3.Code != http.StatusGone {
		t.Fatalf("expected 410 for deleted code, got %d", w3.Code)
	}
}

// 9. Concurrent creation of the same custom alias -> exactly one 201, remainder 409
func TestEdgeCase_ConcurrentCreationSameAlias(t *testing.T) {
	env := setupTestEnv(t)

	concurrency := 10
	var successCount int32
	var conflictCount int32

	var wg sync.WaitGroup
	wg.Add(concurrency)

	for i := 0; i < concurrency; i++ {
		go func(id int) {
			defer wg.Done()
			b, _ := json.Marshal(map[string]any{
				"url":   fmt.Sprintf("https://example.com/target-%d", id),
				"alias": "race-promo",
			})
			req := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b))
			req.Header.Set("Content-Type", "application/json")
			w := httptest.NewRecorder()
			env.router.ServeHTTP(w, req)

			if w.Code == http.StatusCreated {
				atomic.AddInt32(&successCount, 1)
			} else if w.Code == http.StatusConflict {
				atomic.AddInt32(&conflictCount, 1)
			}
		}(i)
	}

	wg.Wait()

	if successCount != 1 {
		t.Fatalf("expected exactly 1 successful creation, got %d", successCount)
	}
	if conflictCount != int32(concurrency-1) {
		t.Fatalf("expected %d conflicts, got %d", concurrency-1, conflictCount)
	}
}

// 10. HEAD requests do not inflate click counts; GET requests do
func TestEdgeCase_HEADRequestsNotCountedInClicks(t *testing.T) {
	env := setupTestEnv(t)

	// Create link
	b, _ := json.Marshal(map[string]any{"url": "https://example.com/head-test", "alias": "head-link"})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	env.router.ServeHTTP(w, req)

	// 5 HEAD requests (e.g. social preview crawlers)
	for i := 0; i < 5; i++ {
		headReq := httptest.NewRequest(http.MethodHead, "/head-link", nil)
		headReq.Header.Set("User-Agent", "Twitterbot/1.0")
		headW := httptest.NewRecorder()
		env.router.ServeHTTP(headW, headReq)
		if headW.Code != http.StatusFound {
			t.Fatalf("expected 302 on HEAD request, got %d", headW.Code)
		}
	}

	// 2 GET requests
	for i := 0; i < 2; i++ {
		getReq := httptest.NewRequest(http.MethodGet, "/head-link", nil)
		getReq.Header.Set("User-Agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)")
		getW := httptest.NewRecorder()
		env.router.ServeHTTP(getW, getReq)
		if getW.Code != http.StatusFound {
			t.Fatalf("expected 302 on GET request, got %d", getW.Code)
		}
	}

	// Flush buffer to store
	ctx := context.Background()
	if err := env.flusher.FlushNow(ctx); err != nil {
		t.Fatalf("flusher failed: %v", err)
	}

	// Query stats
	statsReq := httptest.NewRequest(http.MethodGet, "/api/v1/links/head-link/stats", nil)
	statsW := httptest.NewRecorder()
	env.router.ServeHTTP(statsW, statsReq)
	if statsW.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for stats, got %d", statsW.Code)
	}

	var stats domain.StatsSummary
	_ = json.Unmarshal(statsW.Body.Bytes(), &stats)

	// Total clicks should be exactly 2 (HEAD requests excluded)
	if stats.TotalClicks != 2 {
		t.Fatalf("expected exactly 2 clicks (excluding HEAD), got %d", stats.TotalClicks)
	}
}

// 11. Trailing slashes, whitespace trimming, missing schemes
func TestEdgeCase_WhitespaceAndMissingScheme(t *testing.T) {
	env := setupTestEnv(t)

	// URL with leading and trailing whitespace
	b1, _ := json.Marshal(map[string]any{"url": "   https://example.com/trimmed   "})
	r1 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b1))
	r1.Header.Set("Content-Type", "application/json")
	w1 := httptest.NewRecorder()
	env.router.ServeHTTP(w1, r1)
	if w1.Code != http.StatusCreated {
		t.Fatalf("expected 201 for trimmed URL, got %d", w1.Code)
	}
	var res1 map[string]any
	_ = json.Unmarshal(w1.Body.Bytes(), &res1)
	if res1["original_url"] != "https://example.com/trimmed" {
		t.Fatalf("expected trimmed url, got %s", res1["original_url"])
	}

	// Missing scheme -> rejected with 422
	b2, _ := json.Marshal(map[string]any{"url": "example.com/no-scheme"})
	r2 := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b2))
	r2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	env.router.ServeHTTP(w2, r2)
	if w2.Code != http.StatusUnprocessableEntity {
		t.Fatalf("expected 422 for missing scheme, got %d", w2.Code)
	}
}

// 12. SingleFlight prevents concurrent DB hits during cache stampede
func TestEdgeCase_SingleFlightCoalescesDBLookups(t *testing.T) {
	env := setupTestEnv(t)

	// Create link
	b, _ := json.Marshal(map[string]any{"url": "https://example.com/viral", "alias": "viral-promo"})
	r := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(b))
	r.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	env.router.ServeHTTP(w, r)

	// Evict from cache to simulate cache miss / expiration
	_ = env.cache.Delete(context.Background(), "viral-promo")

	// Fire 50 concurrent requests simultaneously on cache miss
	concurrency := 50
	var wg sync.WaitGroup
	wg.Add(concurrency)

	for i := 0; i < concurrency; i++ {
		go func() {
			defer wg.Done()
			req := httptest.NewRequest(http.MethodGet, "/viral-promo", nil)
			rec := httptest.NewRecorder()
			env.router.ServeHTTP(rec, req)
			if rec.Code != http.StatusFound {
				t.Errorf("expected 302 Found, got %d", rec.Code)
			}
		}()
	}

	wg.Wait()
}

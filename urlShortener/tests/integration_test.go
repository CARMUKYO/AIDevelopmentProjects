package tests

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"urlshortener/internal/domain"
)

func TestFullLifecycle_EndToEnd(t *testing.T) {
	env := setupTestEnv(t)

	// 1. Create a short link
	createPayload := map[string]any{
		"url":   "https://github.com/golang/go",
		"alias": "golang-repo",
	}
	body, _ := json.Marshal(createPayload)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/links", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	env.router.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Fatalf("expected 201 Created, got %d: %s", w.Code, w.Body.String())
	}

	var created domain.Link
	_ = json.Unmarshal(w.Body.Bytes(), &created)
	deleteToken := created.DeleteToken
	if deleteToken == "" {
		t.Fatalf("expected delete_token to be returned in create response")
	}

	// 2. Query metadata
	metaReq := httptest.NewRequest(http.MethodGet, "/api/v1/links/golang-repo", nil)
	metaW := httptest.NewRecorder()
	env.router.ServeHTTP(metaW, metaReq)
	if metaW.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for metadata, got %d", metaW.Code)
	}

	// 3. Perform 3 redirects from different referrers
	referrers := []string{"https://twitter.com/post/1", "https://reddit.com/r/golang", ""}
	for _, ref := range referrers {
		redReq := httptest.NewRequest(http.MethodGet, "/golang-repo", nil)
		if ref != "" {
			redReq.Header.Set("Referer", ref)
		}
		redReq.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
		redW := httptest.NewRecorder()
		env.router.ServeHTTP(redW, redReq)

		if redW.Code != http.StatusFound {
			t.Fatalf("expected 302 Found, got %d", redW.Code)
		}
		if redW.Header().Get("Location") != "https://github.com/golang/go" {
			t.Fatalf("wrong destination: %s", redW.Header().Get("Location"))
		}
	}

	// 4. Flush click buffer
	if err := env.flusher.FlushNow(context.Background()); err != nil {
		t.Fatalf("flush error: %v", err)
	}

	// 5. Query stats
	statsReq := httptest.NewRequest(http.MethodGet, "/api/v1/links/golang-repo/stats", nil)
	statsW := httptest.NewRecorder()
	env.router.ServeHTTP(statsW, statsReq)
	if statsW.Code != http.StatusOK {
		t.Fatalf("expected 200 OK for stats, got %d", statsW.Code)
	}
	var stats domain.StatsSummary
	_ = json.Unmarshal(statsW.Body.Bytes(), &stats)
	if stats.TotalClicks != 3 {
		t.Fatalf("expected 3 total clicks, got %d", stats.TotalClicks)
	}

	// 6. Delete link with wrong token -> 401 Unauthorized
	badDelReq := httptest.NewRequest(http.MethodDelete, "/api/v1/links/golang-repo", nil)
	badDelReq.Header.Set("X-Delete-Token", "wrong-token-value")
	badDelW := httptest.NewRecorder()
	env.router.ServeHTTP(badDelW, badDelReq)
	if badDelW.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401 Unauthorized for bad token, got %d", badDelW.Code)
	}

	// 7. Delete link with correct token -> 204 No Content
	delReq := httptest.NewRequest(http.MethodDelete, "/api/v1/links/golang-repo", nil)
	delReq.Header.Set("X-Delete-Token", deleteToken)
	delW := httptest.NewRecorder()
	env.router.ServeHTTP(delW, delReq)
	if delW.Code != http.StatusNoContent {
		t.Fatalf("expected 204 No Content for delete, got %d", delW.Code)
	}

	// 8. Redirect on deleted link -> 410 Gone
	afterDelReq := httptest.NewRequest(http.MethodGet, "/golang-repo", nil)
	afterDelW := httptest.NewRecorder()
	env.router.ServeHTTP(afterDelW, afterDelReq)
	if afterDelW.Code != http.StatusGone {
		t.Fatalf("expected 410 Gone for deleted link, got %d", afterDelW.Code)
	}
}

package middleware

import (
	"encoding/json"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"urlshortener/internal/domain"
)

type clientRecord struct {
	tokens     float64
	lastUpdate time.Time
}

// RateLimiter implements a token bucket rate limiter per client IP.
type RateLimiter struct {
	mu         sync.Mutex
	records    map[string]*clientRecord
	rate       float64 // tokens per second
	capacity   float64 // max bucket capacity
	cleanupInt time.Duration
}

func NewRateLimiter(requestsPerMinute, burst int) *RateLimiter {
	rate := float64(requestsPerMinute) / 60.0
	if rate <= 0 {
		rate = 1.0
	}
	capacity := float64(burst)
	if capacity <= 0 {
		capacity = 10.0
	}

	rl := &RateLimiter{
		records:    make(map[string]*clientRecord),
		rate:       rate,
		capacity:   capacity,
		cleanupInt: 5 * time.Minute,
	}

	// Periodic cleanup of stale IP records
	go rl.cleanupLoop()

	return rl
}

func (rl *RateLimiter) Limit(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := extractIP(r)

		if !rl.allow(ip) {
			w.Header().Set("Content-Type", "application/json")
			w.Header().Set("Retry-After", "60")
			w.WriteHeader(http.StatusTooManyRequests)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"error": domain.ErrRateLimited,
			})
			return
		}

		next.ServeHTTP(w, r)
	})
}

func (rl *RateLimiter) allow(ip string) bool {
	rl.mu.Lock()
	defer rl.mu.Unlock()

	now := time.Now()
	rec, exists := rl.records[ip]
	if !exists {
		rl.records[ip] = &clientRecord{
			tokens:     rl.capacity - 1,
			lastUpdate: now,
		}
		return true
	}

	// Refill tokens
	elapsed := now.Sub(rec.lastUpdate).Seconds()
	rec.tokens += elapsed * rl.rate
	if rec.tokens > rl.capacity {
		rec.tokens = rl.capacity
	}
	rec.lastUpdate = now

	if rec.tokens >= 1.0 {
		rec.tokens -= 1.0
		return true
	}

	return false
}

func (rl *RateLimiter) cleanupLoop() {
	ticker := time.NewTicker(rl.cleanupInt)
	defer ticker.Stop()

	for range ticker.C {
		rl.mu.Lock()
		cutoff := time.Now().Add(-10 * time.Minute)
		for ip, rec := range rl.records {
			if rec.lastUpdate.Before(cutoff) {
				delete(rl.records, ip)
			}
		}
		rl.mu.Unlock()
	}
}

func extractIP(r *http.Request) string {
	// Respect X-Forwarded-For if behind a proxy
	xff := r.Header.Get("X-Forwarded-For")
	if xff != "" {
		parts := strings.Split(xff, ",")
		if len(parts) > 0 {
			ip := strings.TrimSpace(parts[0])
			if net.ParseIP(ip) != nil {
				return ip
			}
		}
	}

	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err == nil {
		return host
	}
	return r.RemoteAddr
}

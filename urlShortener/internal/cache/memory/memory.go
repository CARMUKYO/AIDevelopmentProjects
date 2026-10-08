package memory

import (
	"context"
	"sync"
	"time"

	"urlshortener/internal/domain"
)

type cacheEntry struct {
	link      *domain.CachedLink
	expiresAt time.Time
}

// Cache provides a thread-safe in-memory cache and click buffer.
type Cache struct {
	mu      sync.RWMutex
	entries map[string]cacheEntry

	// Click buffering to eliminate DB contention
	bufMu     sync.Mutex
	daily     map[int64]map[string]int64
	referrers map[int64]map[string]int64
	devices   map[int64]map[string]int64
}

func New() *Cache {
	return &Cache{
		entries:   make(map[string]cacheEntry),
		daily:     make(map[int64]map[string]int64),
		referrers: make(map[int64]map[string]int64),
		devices:   make(map[int64]map[string]int64),
	}
}

func (c *Cache) Get(ctx context.Context, code string) (*domain.CachedLink, bool, error) {
	c.mu.RLock()
	entry, found := c.entries[code]
	c.mu.RUnlock()

	if !found {
		return nil, false, nil
	}

	if !entry.expiresAt.IsZero() && time.Now().UTC().After(entry.expiresAt) {
		c.mu.Lock()
		delete(c.entries, code)
		c.mu.Unlock()
		return nil, false, nil
	}

	return entry.link, true, nil
}

func (c *Cache) Set(ctx context.Context, code string, link *domain.CachedLink, ttl time.Duration) error {
	var exp time.Time
	if ttl > 0 {
		exp = time.Now().UTC().Add(ttl)
	}

	c.mu.Lock()
	c.entries[code] = cacheEntry{
		link:      link,
		expiresAt: exp,
	}
	c.mu.Unlock()
	return nil
}

func (c *Cache) Delete(ctx context.Context, code string) error {
	c.mu.Lock()
	delete(c.entries, code)
	c.mu.Unlock()
	return nil
}

func (c *Cache) RecordClick(ctx context.Context, linkID int64, referrerHost, deviceFamily string) error {
	today := time.Now().UTC().Format("2006-01-02")

	c.bufMu.Lock()
	defer c.bufMu.Unlock()

	// Daily counts
	if c.daily[linkID] == nil {
		c.daily[linkID] = make(map[string]int64)
	}
	c.daily[linkID][today]++

	// Referrers
	if referrerHost != "" {
		if c.referrers[linkID] == nil {
			c.referrers[linkID] = make(map[string]int64)
		}
		c.referrers[linkID][referrerHost]++
	}

	// Devices
	if deviceFamily != "" {
		if c.devices[linkID] == nil {
			c.devices[linkID] = make(map[string]int64)
		}
		c.devices[linkID][deviceFamily]++
	}

	return nil
}

func (c *Cache) DrainClicks(ctx context.Context) (dailyCounts map[int64]map[string]int64, referrers map[int64]map[string]int64, devices map[int64]map[string]int64, err error) {
	c.bufMu.Lock()
	defer c.bufMu.Unlock()

	dailyCounts = c.daily
	referrers = c.referrers
	devices = c.devices

	// Reset buffers
	c.daily = make(map[int64]map[string]int64)
	c.referrers = make(map[int64]map[string]int64)
	c.devices = make(map[int64]map[string]int64)

	return dailyCounts, referrers, devices, nil
}

func (c *Cache) Ping(ctx context.Context) error {
	return nil
}

func (c *Cache) Close() error {
	return nil
}

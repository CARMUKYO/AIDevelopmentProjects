package domain

import (
	"context"
	"time"
)

// Store defines persistence operations for links and statistics.
type Store interface {
	// CreateLink stores a new link. Returns ErrAliasConflict on duplicate code.
	CreateLink(ctx context.Context, link *Link) error

	// GetLinkByCode retrieves a link by its short code. Returns ErrNotFound if missing.
	GetLinkByCode(ctx context.Context, code string) (*Link, error)

	// DeleteLink soft-deletes a link.
	DeleteLink(ctx context.Context, code string) error

	// GetStats retrieves aggregated click metrics for a link.
	GetStats(ctx context.Context, code string) (*StatsSummary, error)

	// FlushClicksBatch persists accumulated click batches in a single atomic/batched operation.
	FlushClicksBatch(ctx context.Context, dailyCounts map[int64]map[string]int64, referrers map[int64]map[string]int64, devices map[int64]map[string]int64) error

	// PurgeExpired permanently deletes records that expired before the given cutoff date.
	PurgeExpired(ctx context.Context, olderThan time.Time, limit int) (int64, error)

	// Ping checks database connectivity.
	Ping(ctx context.Context) error

	// Close cleans up database connections.
	Close() error
}

// CachedLink represents the lightweight cached link data stored in the cache layer.
type CachedLink struct {
	ID          int64      `json:"id"`
	OriginalURL string     `json:"url"`
	ExpiresAt   *time.Time `json:"expires_at,omitempty"`
	Deleted     bool       `json:"deleted"`
}

// Cache defines the caching and in-memory click buffering operations.
type Cache interface {
	// Get retrieves cached link data. Returns (link, hit, error).
	Get(ctx context.Context, code string) (*CachedLink, bool, error)

	// Set stores link data in cache with given TTL.
	Set(ctx context.Context, code string, link *CachedLink, ttl time.Duration) error

	// Delete removes a key from cache (or marks it as deleted).
	Delete(ctx context.Context, code string) error

	// RecordClick buffers a click event asynchronously to prevent row locking.
	RecordClick(ctx context.Context, linkID int64, referrerHost, deviceFamily string) error

	// DrainClicks extracts buffered clicks for persistence.
	DrainClicks(ctx context.Context) (dailyCounts map[int64]map[string]int64, referrers map[int64]map[string]int64, devices map[int64]map[string]int64, err error)

	// Ping checks cache connectivity.
	Ping(ctx context.Context) error

	// Close cleanly terminates cache connections.
	Close() error
}

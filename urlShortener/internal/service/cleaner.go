package service

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"urlshortener/internal/domain"
)

type ExpiredCleaner struct {
	store     domain.Store
	interval  time.Duration
	retention time.Duration
	batchSize int
	stopCh    chan struct{}
	wg        sync.WaitGroup
}

func NewExpiredCleaner(store domain.Store, interval, retention time.Duration, batchSize int) *ExpiredCleaner {
	if interval <= 0 {
		interval = 24 * time.Hour
	}
	if retention <= 0 {
		retention = 30 * 24 * time.Hour // 30 days retention post-expiration
	}
	if batchSize <= 0 {
		batchSize = 500
	}
	return &ExpiredCleaner{
		store:     store,
		interval:  interval,
		retention: retention,
		batchSize: batchSize,
		stopCh:    make(chan struct{}),
	}
}

func (c *ExpiredCleaner) Start() {
	c.wg.Add(1)
	go func() {
		defer c.wg.Done()
		ticker := time.NewTicker(c.interval)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				c.cleanup()
			case <-c.stopCh:
				return
			}
		}
	}()
}

func (c *ExpiredCleaner) Stop() {
	close(c.stopCh)
	c.wg.Wait()
}

func (c *ExpiredCleaner) PurgeOnce(ctx context.Context) (int64, error) {
	cutoff := time.Now().UTC().Add(-c.retention)
	var totalDeleted int64

	for {
		deleted, err := c.store.PurgeExpired(ctx, cutoff, c.batchSize)
		if err != nil {
			return totalDeleted, err
		}
		totalDeleted += deleted
		if deleted < int64(c.batchSize) {
			break
		}
		// Pause between batches to avoid table lock escalation
		select {
		case <-ctx.Done():
			return totalDeleted, ctx.Err()
		case <-time.After(100 * time.Millisecond):
		}
	}

	return totalDeleted, nil
}

func (c *ExpiredCleaner) cleanup() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	deleted, err := c.PurgeOnce(ctx)
	if err != nil {
		slog.Error("failed to purge expired links", "error", err)
	} else if deleted > 0 {
		slog.Info("purged expired links", "count", deleted)
	}
}

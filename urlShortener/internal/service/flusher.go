package service

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"urlshortener/internal/domain"
)

type ClickFlusher struct {
	store    domain.Store
	cache    domain.Cache
	interval time.Duration
	stopCh   chan struct{}
	wg       sync.WaitGroup
}

func NewClickFlusher(store domain.Store, cache domain.Cache, interval time.Duration) *ClickFlusher {
	if interval <= 0 {
		interval = 5 * time.Second
	}
	return &ClickFlusher{
		store:    store,
		cache:    cache,
		interval: interval,
		stopCh:   make(chan struct{}),
	}
}

// Start launches the background flusher ticker.
func (f *ClickFlusher) Start() {
	f.wg.Add(1)
	go func() {
		defer f.wg.Done()
		ticker := time.NewTicker(f.interval)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				f.flush()
			case <-f.stopCh:
				f.flush() // Drain on shutdown
				return
			}
		}
	}()
}

// Stop gracefully signals the flusher to drain remaining clicks and stops.
func (f *ClickFlusher) Stop() {
	close(f.stopCh)
	f.wg.Wait()
}

// FlushNow triggers an immediate drain and flush.
func (f *ClickFlusher) FlushNow(ctx context.Context) error {
	daily, referrers, devices, err := f.cache.DrainClicks(ctx)
	if err != nil {
		return err
	}
	if len(daily) == 0 && len(referrers) == 0 && len(devices) == 0 {
		return nil
	}
	return f.store.FlushClicksBatch(ctx, daily, referrers, devices)
}

func (f *ClickFlusher) flush() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := f.FlushNow(ctx); err != nil {
		slog.Error("failed to flush click metrics batch", "error", err)
	}
}

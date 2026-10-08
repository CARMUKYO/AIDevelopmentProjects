package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"urlshortener/internal/api"
	"urlshortener/internal/api/middleware"
	memcache "urlshortener/internal/cache/memory"
	rediscache "urlshortener/internal/cache/redis"
	"urlshortener/internal/clock"
	"urlshortener/internal/config"
	"urlshortener/internal/domain"
	"urlshortener/internal/service"
	pgstorage "urlshortener/internal/storage/postgres"
	sqlitestorage "urlshortener/internal/storage/sqlite"
	"urlshortener/internal/validator"
)

func main() {
	cfg := config.Load()

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	slog.Info("starting URL shortener service", "port", cfg.Port, "db_driver", cfg.DBDriver)

	// 1. Storage setup
	var store domain.Store
	var err error

	if cfg.DBDriver == "postgres" {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		store, err = pgstorage.New(ctx, cfg.DatabaseURL)
		if err != nil {
			slog.Error("failed to connect to postgresql", "error", err)
			os.Exit(1)
		}
		slog.Info("connected to postgresql database")
	} else {
		store, err = sqlitestorage.New(cfg.DatabaseURL)
		if err != nil {
			slog.Error("failed to initialize sqlite database", "error", err)
			os.Exit(1)
		}
		slog.Info("initialized sqlite database", "path", cfg.DatabaseURL)
	}
	defer store.Close()

	// 2. Cache setup
	var cache domain.Cache
	if cfg.RedisURL != "" {
		cache, err = rediscache.New(cfg.RedisURL)
		if err != nil {
			slog.Warn("redis connection failed, falling back to in-memory cache", "error", err)
			cache = memcache.New()
		} else {
			slog.Info("connected to redis cache")
		}
	} else {
		cache = memcache.New()
		slog.Info("using in-memory cache & buffer")
	}
	defer cache.Close()

	// 3. Components & Services
	clk := clock.NewRealClock()
	val := validator.NewValidator(cfg.ServerDomain)
	linkSvc := service.NewLinkService(store, cache, clk, val)

	// 4. Background workers
	flusher := service.NewClickFlusher(store, cache, time.Duration(cfg.FlushIntervalSec)*time.Second)
	flusher.Start()

	cleaner := service.NewExpiredCleaner(store, time.Duration(cfg.CleanerIntervalHr)*time.Hour, 30*24*time.Hour, 500)
	cleaner.Start()

	// 5. HTTP Router & Server
	rateLimiter := middleware.NewRateLimiter(cfg.RateLimitPerMin, cfg.RateLimitBurst)
	handler := api.NewHandler(linkSvc, cfg.BaseURL, store, cache)
	router := api.SetupRouter(handler, rateLimiter)

	srv := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           router,
		ReadTimeout:       5 * time.Second,
		ReadHeaderTimeout: 2 * time.Second,
		WriteTimeout:      10 * time.Second,
		IdleTimeout:       120 * time.Second,
	}

	// 6. Graceful shutdown handler
	shutdownCh := make(chan os.Signal, 1)
	signal.Notify(shutdownCh, os.Interrupt, syscall.SIGTERM)

	go func() {
		slog.Info("HTTP server listening", "addr", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("HTTP server failed", "error", err)
			os.Exit(1)
		}
	}()

	<-shutdownCh
	slog.Info("shutdown signal received, commencing graceful teardown")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		slog.Error("HTTP server shutdown error", "error", err)
	}

	slog.Info("flushing remaining click metrics to database")
	flusher.Stop()
	cleaner.Stop()

	slog.Info("service stopped cleanly")
}

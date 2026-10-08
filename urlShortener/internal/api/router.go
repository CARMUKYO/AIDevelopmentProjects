package api

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"urlshortener/internal/api/middleware"
)

// SetupRouter constructs the Chi HTTP multiplexer and registers all routes.
func SetupRouter(h *Handler, rateLimiter *middleware.RateLimiter) http.Handler {
	r := chi.NewRouter()

	// Base middlewares
	r.Use(chimw.RequestID)
	r.Use(chimw.RealIP)
	r.Use(chimw.Logger)
	r.Use(chimw.Recoverer)
	r.Use(middleware.LimitBodySize)

	// Health check endpoint
	r.Get("/health", h.HealthCheck)

	// Version 1 API routes
	r.Route("/api/v1", func(v1 chi.Router) {
		// Create link with rate limiting
		v1.With(rateLimiter.Limit).Post("/links", h.CreateLink)

		// Link management & statistics
		v1.Get("/links/{code}", h.GetLinkMetadata)
		v1.Get("/links/{code}/stats", h.GetStats)
		v1.Delete("/links/{code}", h.DeleteLink)
	})

	// Redirect hot path registered AFTER fixed system routes
	r.Get("/{code}", h.Redirect)
	r.Head("/{code}", h.Redirect)

	return r
}

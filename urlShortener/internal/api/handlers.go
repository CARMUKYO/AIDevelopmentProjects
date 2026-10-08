package api

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/go-chi/chi/v5"
	"urlshortener/internal/domain"
	"urlshortener/internal/service"
)

type Handler struct {
	svc      *service.LinkService
	baseURL  string
	store    domain.Store
	cache    domain.Cache
}

func NewHandler(svc *service.LinkService, baseURL string, store domain.Store, cache domain.Cache) *Handler {
	trimmedBase := strings.TrimRight(baseURL, "/")
	return &Handler{
		svc:     svc,
		baseURL: trimmedBase,
		store:   store,
		cache:   cache,
	}
}

// CreateLink handles POST /api/v1/links
func (h *Handler) CreateLink(w http.ResponseWriter, r *http.Request) {
	var req service.CreateLinkRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		h.writeError(w, &domain.AppError{
			Code:       "INVALID_REQUEST",
			Message:    "Malformed JSON request body.",
			HTTPStatus: http.StatusBadRequest,
		})
		return
	}

	link, err := h.svc.Create(r.Context(), req)
	if err != nil {
		h.writeError(w, err)
		return
	}

	resp := map[string]any{
		"code":         link.Code,
		"short_url":    fmt.Sprintf("%s/%s", h.baseURL, link.Code),
		"original_url": link.OriginalURL,
		"created_at":   link.CreatedAt,
		"expires_at":   link.ExpiresAt,
		"delete_token": link.DeleteToken,
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	_ = json.NewEncoder(w).Encode(resp)
}

// GetLinkMetadata handles GET /api/v1/links/{code}
func (h *Handler) GetLinkMetadata(w http.ResponseWriter, r *http.Request) {
	code := chi.URLParam(r, "code")
	link, err := h.svc.GetLinkMetadata(r.Context(), code)
	if err != nil {
		h.writeError(w, err)
		return
	}

	resp := map[string]any{
		"code":         link.Code,
		"short_url":    fmt.Sprintf("%s/%s", h.baseURL, link.Code),
		"original_url": link.OriginalURL,
		"created_at":   link.CreatedAt,
		"expires_at":   link.ExpiresAt,
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

// GetStats handles GET /api/v1/links/{code}/stats
func (h *Handler) GetStats(w http.ResponseWriter, r *http.Request) {
	code := chi.URLParam(r, "code")
	stats, err := h.svc.GetStats(r.Context(), code)
	if err != nil {
		h.writeError(w, err)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(stats)
}

// DeleteLink handles DELETE /api/v1/links/{code}
func (h *Handler) DeleteLink(w http.ResponseWriter, r *http.Request) {
	code := chi.URLParam(r, "code")
	token := r.Header.Get("X-Delete-Token")
	if token == "" {
		h.writeError(w, domain.ErrUnauthorized)
		return
	}

	if err := h.svc.Delete(r.Context(), code, token); err != nil {
		h.writeError(w, err)
		return
	}

	w.WriteHeader(http.StatusNoContent)
}

// Redirect handles GET /{code}
func (h *Handler) Redirect(w http.ResponseWriter, r *http.Request) {
	code := chi.URLParam(r, "code")

	// Disallow counting HEAD requests as clicks
	isClick := (r.Method == http.MethodGet)

	// Extract referrer host safely (stripping path and query parameters)
	referrerHost := extractReferrerHost(r.Header.Get("Referer"))

	// Extract coarse device family
	deviceFamily := categorizeDevice(r.Header.Get("User-Agent"))

	destURL, err := h.svc.Resolve(r.Context(), code, referrerHost, deviceFamily, isClick)
	if err != nil {
		h.writeError(w, err)
		return
	}

	// Enforce no client-side caching to ensure clicks and expiration are tracked
	w.Header().Set("Cache-Control", "private, max-age=0, no-cache")
	http.Redirect(w, r, destURL, http.StatusFound)
}

// HealthCheck handles GET /health
func (h *Handler) HealthCheck(w http.ResponseWriter, r *http.Request) {
	dbStatus := "up"
	if err := h.store.Ping(r.Context()); err != nil {
		dbStatus = "down"
	}

	cacheStatus := "up"
	if h.cache != nil {
		if err := h.cache.Ping(r.Context()); err != nil {
			cacheStatus = "down"
		}
	}

	status := http.StatusOK
	if dbStatus == "down" {
		status = http.StatusServiceUnavailable
	}

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"status":   "ok",
		"database": dbStatus,
		"cache":    cacheStatus,
	})
}

func (h *Handler) writeError(w http.ResponseWriter, err error) {
	appErr := domain.AsAppError(err)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(appErr.HTTPStatus)
	_ = json.NewEncoder(w).Encode(map[string]any{
		"error": appErr,
	})
}

func extractReferrerHost(ref string) string {
	if ref == "" {
		return "direct"
	}
	parsed, err := url.Parse(ref)
	if err != nil || parsed.Hostname() == "" {
		return "other"
	}
	return strings.ToLower(parsed.Hostname())
}

func categorizeDevice(ua string) string {
	if ua == "" {
		return "Other"
	}
	lower := strings.ToLower(ua)

	// Bots and crawlers
	if strings.Contains(lower, "bot") ||
		strings.Contains(lower, "crawler") ||
		strings.Contains(lower, "spider") ||
		strings.Contains(lower, "slackbot") ||
		strings.Contains(lower, "twitterbot") ||
		strings.Contains(lower, "facebookexternalhit") ||
		strings.Contains(lower, "whatsapp") ||
		strings.Contains(lower, "discordbot") {
		return "Bot"
	}

	// Mobile / Tablet / Desktop
	if strings.Contains(lower, "ipad") || strings.Contains(lower, "tablet") {
		return "Tablet"
	}
	if strings.Contains(lower, "mobile") || strings.Contains(lower, "android") || strings.Contains(lower, "iphone") {
		return "Mobile"
	}

	return "Desktop"
}

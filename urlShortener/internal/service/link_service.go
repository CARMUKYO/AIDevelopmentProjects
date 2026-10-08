package service

import (
	"context"
	"crypto/subtle"
	"errors"
	"fmt"
	"time"

	"golang.org/x/sync/singleflight"
	"urlshortener/internal/clock"
	"urlshortener/internal/domain"
	"urlshortener/internal/idgen"
	"urlshortener/internal/validator"
)

const (
	MaxCollisionRetries = 5
	DefaultCacheTTL     = 1 * time.Hour
	NegativeCacheTTL    = 60 * time.Second
)

type CreateLinkRequest struct {
	URL       string     `json:"url"`
	Alias     string     `json:"alias,omitempty"`
	ExpiresAt *time.Time `json:"expires_at,omitempty"`
}

type LinkService struct {
	store     domain.Store
	cache     domain.Cache
	clk       clock.Clock
	idGen     *idgen.Generator
	val       *validator.Validator
	sfGroup   singleflight.Group
}

func NewLinkService(store domain.Store, cache domain.Cache, clk clock.Clock, val *validator.Validator) *LinkService {
	return &LinkService{
		store:   store,
		cache:   cache,
		clk:     clk,
		idGen:   idgen.NewGenerator(),
		val:     val,
	}
}

// Create generates or validates a short link and persists it.
func (s *LinkService) Create(ctx context.Context, req CreateLinkRequest) (*domain.Link, error) {
	// 1. Validate destination URL
	normalizedURL, err := s.val.ValidateURL(req.URL)
	if err != nil {
		return nil, err
	}

	// 2. Validate expiration if provided
	now := s.clk.Now()
	if req.ExpiresAt != nil {
		if !req.ExpiresAt.After(now) {
			return nil, domain.ErrInvalidExpiration
		}
	}

	// 3. Generate delete management token
	deleteToken, err := s.idGen.GenerateDeleteToken()
	if err != nil {
		return nil, fmt.Errorf("failed to generate management token: %w", err)
	}

	// 4. Handle custom alias vs generated code
	var code string
	var isCustom bool

	if req.Alias != "" {
		if err := s.val.ValidateCustomAlias(req.Alias); err != nil {
			return nil, err
		}
		code = req.Alias
		isCustom = true

		link := &domain.Link{
			Code:        code,
			OriginalURL: normalizedURL,
			IsCustom:    isCustom,
			DeleteToken: deleteToken,
			CreatedAt:   now,
			ExpiresAt:   req.ExpiresAt,
		}

		if err := s.store.CreateLink(ctx, link); err != nil {
			return nil, err
		}

		s.warmCache(ctx, link)
		return link, nil
	}

	// Auto-generated Base62 code with retry loop on collision
	for attempt := 0; attempt < MaxCollisionRetries; attempt++ {
		code, err = s.idGen.GenerateCode()
		if err != nil {
			return nil, err
		}

		link := &domain.Link{
			Code:        code,
			OriginalURL: normalizedURL,
			IsCustom:    false,
			DeleteToken: deleteToken,
			CreatedAt:   now,
			ExpiresAt:   req.ExpiresAt,
		}

		err = s.store.CreateLink(ctx, link)
		if err == nil {
			s.warmCache(ctx, link)
			return link, nil
		}

		if !errors.Is(err, domain.ErrAliasConflict) {
			return nil, err
		}
		// Collided with existing code; retry with new code
	}

	return nil, fmt.Errorf("failed to generate unique short code after %d attempts", MaxCollisionRetries)
}

// Resolve looks up a short code for redirection, enforcing cache, SingleFlight, and expiration.
func (s *LinkService) Resolve(ctx context.Context, code string, referrerHost, deviceFamily string, isClick bool) (string, error) {
	now := s.clk.Now()

	// 1. Check Cache
	if s.cache != nil {
		cached, hit, err := s.cache.Get(ctx, code)
		if err != nil {
			if errors.Is(err, domain.ErrNotFound) || errors.Is(err, domain.ErrDeleted) {
				return "", err
			}
		} else if hit && cached != nil {
			if cached.Deleted {
				return "", domain.ErrDeleted
			}
			// Verify expiration against injected clock
			if cached.ExpiresAt != nil && !now.Before(*cached.ExpiresAt) {
				return "", domain.ErrExpired
			}
			// Asynchronously record click
			if isClick {
				s.recordClickAsync(ctx, cached.ID, referrerHost, deviceFamily)
			}
			return cached.OriginalURL, nil
		}
	}

	// 2. Cache Miss: SingleFlight group coalesces concurrent DB hits
	val, err, _ := s.sfGroup.Do(code, func() (any, error) {
		// Use detached context with timeout to avoid one client's cancellation failing all concurrent waiters
		dbCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()

		link, err := s.store.GetLinkByCode(dbCtx, code)
		if err != nil {
			if errors.Is(err, domain.ErrNotFound) && s.cache != nil {
				// Negative caching
				_ = s.cache.Set(dbCtx, code, nil, NegativeCacheTTL)
			}
			return nil, err
		}
		s.warmCache(dbCtx, link)
		return link, nil
	})

	if err != nil {
		return "", err
	}

	link := val.(*domain.Link)

	// Check soft deletion
	if link.IsDeleted() {
		return "", domain.ErrDeleted
	}

	// Check expiration against clock
	if link.IsExpired(now) {
		return "", domain.ErrExpired
	}

	// Record click
	if isClick {
		s.recordClickAsync(ctx, link.ID, referrerHost, deviceFamily)
	}

	return link.OriginalURL, nil
}

// GetLinkMetadata returns public metadata for a link.
func (s *LinkService) GetLinkMetadata(ctx context.Context, code string) (*domain.Link, error) {
	link, err := s.store.GetLinkByCode(ctx, code)
	if err != nil {
		return nil, err
	}
	if link.IsDeleted() {
		return nil, domain.ErrDeleted
	}
	if link.IsExpired(s.clk.Now()) {
		return nil, domain.ErrExpired
	}
	return link, nil
}

// GetStats returns aggregated statistics for a link.
func (s *LinkService) GetStats(ctx context.Context, code string) (*domain.StatsSummary, error) {
	stats, err := s.store.GetStats(ctx, code)
	if err != nil {
		return nil, err
	}
	if stats.ExpiresAt != nil && !s.clk.Now().Before(*stats.ExpiresAt) {
		return nil, domain.ErrExpired
	}
	return stats, nil
}

// Delete removes a link if the provided token matches.
func (s *LinkService) Delete(ctx context.Context, code, token string) error {
	link, err := s.store.GetLinkByCode(ctx, code)
	if err != nil {
		return err
	}

	if link.IsDeleted() {
		return domain.ErrNotFound
	}

	// Constant-time token verification to eliminate timing attacks
	if subtle.ConstantTimeCompare([]byte(link.DeleteToken), []byte(token)) != 1 {
		return domain.ErrUnauthorized
	}

	if err := s.store.DeleteLink(ctx, code); err != nil {
		return err
	}

	if s.cache != nil {
		_ = s.cache.Delete(ctx, code)
	}

	return nil
}

func (s *LinkService) warmCache(ctx context.Context, link *domain.Link) {
	if s.cache == nil || link == nil {
		return
	}

	ttl := DefaultCacheTTL
	if link.ExpiresAt != nil {
		remaining := link.ExpiresAt.Sub(s.clk.Now())
		if remaining <= 0 {
			return
		}
		if remaining < ttl {
			ttl = remaining
		}
	}

	cached := &domain.CachedLink{
		ID:          link.ID,
		OriginalURL: link.OriginalURL,
		ExpiresAt:   link.ExpiresAt,
		Deleted:     link.IsDeleted(),
	}

	_ = s.cache.Set(ctx, link.Code, cached, ttl)
}

func (s *LinkService) recordClickAsync(ctx context.Context, linkID int64, referrerHost, deviceFamily string) {
	if s.cache != nil {
		_ = s.cache.RecordClick(ctx, linkID, referrerHost, deviceFamily)
	}
}

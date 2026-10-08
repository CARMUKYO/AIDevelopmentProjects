package validator

import (
	"fmt"
	"net"
	"net/url"
	"strings"

	"golang.org/x/net/idna"
	"urlshortener/internal/domain"
	"urlshortener/internal/idgen"
)

const (
	MaxURLLength = 2048
)

// ReservedWords contains system paths that cannot be claimed as custom aliases.
var ReservedWords = map[string]bool{
	"api":         true,
	"health":      true,
	"metrics":     true,
	"stats":       true,
	"admin":       true,
	"static":      true,
	"assets":      true,
	"favicon.ico": true,
	"robots.txt":  true,
	"sitemap.xml": true,
	"docs":        true,
	"swagger":     true,
	"v1":          true,
	"v2":          true,
	"auth":        true,
	"login":       true,
	"register":    true,
	"dashboard":   true,
}

// Validator encapsulates URL and alias validation logic.
type Validator struct {
	serverDomain string // The shortener's own domain, e.g. "sho.rt" or "localhost:8080"
}

func NewValidator(serverDomain string) *Validator {
	// Normalize domain (strip port if present, lowercase)
	domainOnly := strings.ToLower(serverDomain)
	if h, _, err := net.SplitHostPort(domainOnly); err == nil {
		domainOnly = h
	}
	return &Validator{serverDomain: domainOnly}
}

// ValidateURL validates and normalizes a destination URL.
func (v *Validator) ValidateURL(rawURL string) (string, error) {
	trimmed := strings.TrimSpace(rawURL)
	if trimmed == "" {
		return "", &domain.AppError{
			Code:       "INVALID_URL",
			Message:    "URL cannot be empty.",
			HTTPStatus: 422,
		}
	}

	if len(trimmed) > MaxURLLength {
		return "", &domain.AppError{
			Code:       "INVALID_URL",
			Message:    fmt.Sprintf("URL exceeds maximum length of %d characters.", MaxURLLength),
			HTTPStatus: 422,
		}
	}

	parsed, err := url.Parse(trimmed)
	if err != nil || parsed.Host == "" {
		return "", &domain.AppError{
			Code:       "INVALID_URL",
			Message:    "URL must be a valid, fully qualified address including scheme and host.",
			HTTPStatus: 422,
		}
	}

	// Scheme check: strictly http and https
	scheme := strings.ToLower(parsed.Scheme)
	if scheme != "http" && scheme != "https" {
		return "", domain.ErrInvalidScheme
	}

	// Extract hostname (without port)
	host := strings.ToLower(parsed.Hostname())
	if host == "" {
		return "", domain.ErrInvalidURL
	}

	// Convert Internationalized Domain Names (IDN) to ASCII punycode if needed
	asciiHost, err := idna.ToASCII(host)
	if err != nil {
		return "", &domain.AppError{
			Code:       "INVALID_URL",
			Message:    "Invalid internationalized domain name.",
			HTTPStatus: 422,
		}
	}

	// Self-referential loop check
	if v.serverDomain != "" && (asciiHost == v.serverDomain || host == v.serverDomain) {
		return "", domain.ErrRedirectLoop
	}

	// SSRF and private IP blocking
	if isBlockedHost(asciiHost) {
		return "", &domain.AppError{
			Code:       "INVALID_URL",
			Message:    "Target URL resolves to a restricted or loopback destination.",
			HTTPStatus: 422,
		}
	}

	// Reconstruct normalized URL with ASCII host
	if parsed.Port() != "" {
		parsed.Host = net.JoinHostPort(asciiHost, parsed.Port())
	} else {
		parsed.Host = asciiHost
	}

	return parsed.String(), nil
}

// ValidateCustomAlias checks custom alias formatting and reserved words.
func (v *Validator) ValidateCustomAlias(alias string) error {
	trimmed := strings.TrimSpace(alias)
	if err := idgen.ValidateAlias(trimmed); err != nil {
		return &domain.AppError{
			Code:       "INVALID_ALIAS",
			Message:    err.Error(),
			HTTPStatus: 422,
		}
	}

	// Reserved word check (case-insensitive)
	lower := strings.ToLower(trimmed)
	if ReservedWords[lower] {
		return domain.ErrReservedAlias
	}

	return nil
}

// isBlockedHost checks for localhost, link-local, or private IPs.
func isBlockedHost(host string) bool {
	if host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "0.0.0.0" {
		return true
	}
	// AWS / Cloud metadata service
	if host == "169.254.169.254" {
		return true
	}

	// Check if host is a literal IP
	ip := net.ParseIP(host)
	if ip != nil {
		if ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsUnspecified() || ip.IsMulticast() {
			return true
		}
	}
	return false
}

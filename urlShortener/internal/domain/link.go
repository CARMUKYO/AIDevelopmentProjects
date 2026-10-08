package domain

import "time"

// Link represents a shortened URL entry in the system.
type Link struct {
	ID          int64      `json:"id"`
	Code        string     `json:"code"`
	OriginalURL string     `json:"original_url"`
	IsCustom    bool       `json:"is_custom"`
	DeleteToken string     `json:"delete_token,omitempty"` // Omitted in public responses
	CreatedAt   time.Time  `json:"created_at"`
	ExpiresAt   *time.Time `json:"expires_at,omitempty"`
	DeletedAt   *time.Time `json:"deleted_at,omitempty"`
}

// IsExpired checks if the link is expired relative to a given point in time.
func (l *Link) IsExpired(now time.Time) bool {
	if l.ExpiresAt == nil {
		return false
	}
	return !now.Before(*l.ExpiresAt)
}

// IsDeleted checks if the link has been soft-deleted.
func (l *Link) IsDeleted() bool {
	return l.DeletedAt != nil
}

// DailyClicks represents aggregate click stats for a specific day.
type DailyClicks struct {
	Date   string `json:"date"`
	Clicks int64  `json:"clicks"`
}

// ReferrerStats represents aggregated hits per referrer host.
type ReferrerStats struct {
	Referrer string `json:"referrer"`
	Clicks   int64  `json:"clicks"`
}

// DeviceStats represents aggregated hits per device family.
type DeviceStats struct {
	Family string `json:"family"`
	Clicks int64  `json:"clicks"`
}

// StatsSummary represents the full metrics response for a short link.
type StatsSummary struct {
	Code         string          `json:"code"`
	OriginalURL  string          `json:"original_url"`
	CreatedAt    time.Time       `json:"created_at"`
	ExpiresAt    *time.Time      `json:"expires_at,omitempty"`
	TotalClicks  int64           `json:"total_clicks"`
	DailyClicks  []DailyClicks   `json:"daily_clicks"`
	TopReferrers []ReferrerStats `json:"top_referrers"`
	Devices      []DeviceStats   `json:"devices"`
}

// ClickEvent represents an in-flight click to be buffered and recorded.
type ClickEvent struct {
	LinkID       int64
	Timestamp    time.Time
	ReferrerHost string
	DeviceFamily string
}

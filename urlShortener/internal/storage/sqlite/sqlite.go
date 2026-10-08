package sqlite

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	_ "modernc.org/sqlite"
	"urlshortener/internal/domain"
)

type Store struct {
	db *sql.DB
}

// New creates and initializes a SQLite store with the schema applied.
func New(dataSourceName string) (*Store, error) {
	db, err := sql.Open("sqlite", dataSourceName)
	if err != nil {
		return nil, fmt.Errorf("failed to open sqlite database: %w", err)
	}

	// SQLite connection settings
	db.SetMaxOpenConns(1) // Avoid table lock concurrency issues in SQLite
	db.SetMaxIdleConns(1)

	s := &Store{db: db}
	if err := s.initSchema(context.Background()); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to initialize sqlite schema: %w", err)
	}

	return s, nil
}

func (s *Store) initSchema(ctx context.Context) error {
	schema := `
	CREATE TABLE IF NOT EXISTS links (
		id              INTEGER PRIMARY KEY AUTOINCREMENT,
		code            TEXT NOT NULL UNIQUE,
		original_url    TEXT NOT NULL,
		is_custom       INTEGER NOT NULL DEFAULT 0,
		delete_token    TEXT NOT NULL,
		created_at      TEXT NOT NULL,
		expires_at      TEXT NULL,
		deleted_at      TEXT NULL
	);

	CREATE INDEX IF NOT EXISTS idx_links_code_active 
		ON links (code) 
		WHERE deleted_at IS NULL;

	CREATE INDEX IF NOT EXISTS idx_links_expires_at 
		ON links (expires_at) 
		WHERE expires_at IS NOT NULL AND deleted_at IS NULL;

	CREATE TABLE IF NOT EXISTS link_clicks_daily (
		link_id         INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
		click_date      TEXT NOT NULL,
		click_count     INTEGER NOT NULL DEFAULT 0,
		PRIMARY KEY (link_id, click_date)
	);

	CREATE TABLE IF NOT EXISTS link_referrer_stats (
		link_id         INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
		referrer_host   TEXT NOT NULL,
		click_count     INTEGER NOT NULL DEFAULT 0,
		PRIMARY KEY (link_id, referrer_host)
	);

	CREATE TABLE IF NOT EXISTS link_device_stats (
		link_id         INTEGER NOT NULL REFERENCES links(id) ON DELETE CASCADE,
		device_family   TEXT NOT NULL,
		click_count     INTEGER NOT NULL DEFAULT 0,
		PRIMARY KEY (link_id, device_family)
	);
	`
	_, err := s.db.ExecContext(ctx, schema)
	return err
}

func (s *Store) CreateLink(ctx context.Context, link *domain.Link) error {
	query := `
	INSERT INTO links (code, original_url, is_custom, delete_token, created_at, expires_at, deleted_at)
	VALUES (?, ?, ?, ?, ?, ?, ?)
	`
	var expiresAt, deletedAt *string
	if link.ExpiresAt != nil {
		expStr := link.ExpiresAt.UTC().Format(time.RFC3339Nano)
		expiresAt = &expStr
	}
	if link.DeletedAt != nil {
		delStr := link.DeletedAt.UTC().Format(time.RFC3339Nano)
		deletedAt = &delStr
	}
	createdAt := link.CreatedAt.UTC().Format(time.RFC3339Nano)
	isCustom := 0
	if link.IsCustom {
		isCustom = 1
	}

	res, err := s.db.ExecContext(ctx, query, link.Code, link.OriginalURL, isCustom, link.DeleteToken, createdAt, expiresAt, deletedAt)
	if err != nil {
		if strings.Contains(err.Error(), "UNIQUE constraint failed") || strings.Contains(err.Error(), "constraint failed") {
			return domain.ErrAliasConflict
		}
		return err
	}

	id, err := res.LastInsertId()
	if err != nil {
		return err
	}
	link.ID = id
	return nil
}

func (s *Store) GetLinkByCode(ctx context.Context, code string) (*domain.Link, error) {
	query := `
	SELECT id, code, original_url, is_custom, delete_token, created_at, expires_at, deleted_at
	FROM links
	WHERE code = ?
	`
	row := s.db.QueryRowContext(ctx, query, code)

	var l domain.Link
	var isCustom int
	var createdAtStr string
	var expiresAtStr, deletedAtStr sql.NullString

	err := row.Scan(&l.ID, &l.Code, &l.OriginalURL, &isCustom, &l.DeleteToken, &createdAtStr, &expiresAtStr, &deletedAtStr)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, domain.ErrNotFound
		}
		return nil, err
	}

	l.IsCustom = (isCustom == 1)
	if t, err := time.Parse(time.RFC3339Nano, createdAtStr); err == nil {
		l.CreatedAt = t.UTC()
	} else if t, err := time.Parse(time.RFC3339, createdAtStr); err == nil {
		l.CreatedAt = t.UTC()
	}

	if expiresAtStr.Valid {
		if t, err := time.Parse(time.RFC3339Nano, expiresAtStr.String); err == nil {
			utc := t.UTC()
			l.ExpiresAt = &utc
		} else if t, err := time.Parse(time.RFC3339, expiresAtStr.String); err == nil {
			utc := t.UTC()
			l.ExpiresAt = &utc
		}
	}

	if deletedAtStr.Valid {
		if t, err := time.Parse(time.RFC3339Nano, deletedAtStr.String); err == nil {
			utc := t.UTC()
			l.DeletedAt = &utc
		} else if t, err := time.Parse(time.RFC3339, deletedAtStr.String); err == nil {
			utc := t.UTC()
			l.DeletedAt = &utc
		}
	}

	return &l, nil
}

func (s *Store) DeleteLink(ctx context.Context, code string) error {
	nowStr := time.Now().UTC().Format(time.RFC3339Nano)
	query := `
	UPDATE links
	SET deleted_at = ?
	WHERE code = ? AND deleted_at IS NULL
	`
	res, err := s.db.ExecContext(ctx, query, nowStr, code)
	if err != nil {
		return err
	}
	rows, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if rows == 0 {
		return domain.ErrNotFound
	}
	return nil
}

func (s *Store) GetStats(ctx context.Context, code string) (*domain.StatsSummary, error) {
	link, err := s.GetLinkByCode(ctx, code)
	if err != nil {
		return nil, err
	}

	summary := &domain.StatsSummary{
		Code:         link.Code,
		OriginalURL:  link.OriginalURL,
		CreatedAt:    link.CreatedAt,
		ExpiresAt:    link.ExpiresAt,
		DailyClicks:  make([]domain.DailyClicks, 0),
		TopReferrers: make([]domain.ReferrerStats, 0),
		Devices:      make([]domain.DeviceStats, 0),
	}

	// 1. Daily clicks
	dailyRows, err := s.db.QueryContext(ctx, `
		SELECT click_date, click_count 
		FROM link_clicks_daily 
		WHERE link_id = ? 
		ORDER BY click_date ASC
	`, link.ID)
	if err == nil {
		defer dailyRows.Close()
		var total int64
		for dailyRows.Next() {
			var d domain.DailyClicks
			if err := dailyRows.Scan(&d.Date, &d.Clicks); err == nil {
				summary.DailyClicks = append(summary.DailyClicks, d)
				total += d.Clicks
			}
		}
		summary.TotalClicks = total
	}

	// 2. Referrers
	refRows, err := s.db.QueryContext(ctx, `
		SELECT referrer_host, click_count 
		FROM link_referrer_stats 
		WHERE link_id = ? 
		ORDER BY click_count DESC 
		LIMIT 10
	`, link.ID)
	if err == nil {
		defer refRows.Close()
		for refRows.Next() {
			var r domain.ReferrerStats
			if err := refRows.Scan(&r.Referrer, &r.Clicks); err == nil {
				summary.TopReferrers = append(summary.TopReferrers, r)
			}
		}
	}

	// 3. Devices
	devRows, err := s.db.QueryContext(ctx, `
		SELECT device_family, click_count 
		FROM link_device_stats 
		WHERE link_id = ? 
		ORDER BY click_count DESC
	`, link.ID)
	if err == nil {
		defer devRows.Close()
		for devRows.Next() {
			var d domain.DeviceStats
			if err := devRows.Scan(&d.Family, &d.Clicks); err == nil {
				summary.Devices = append(summary.Devices, d)
			}
		}
	}

	return summary, nil
}

func (s *Store) FlushClicksBatch(ctx context.Context, dailyCounts map[int64]map[string]int64, referrers map[int64]map[string]int64, devices map[int64]map[string]int64) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	// 1. Flush daily counts
	dailyStmt, err := tx.PrepareContext(ctx, `
		INSERT INTO link_clicks_daily (link_id, click_date, click_count)
		VALUES (?, ?, ?)
		ON CONFLICT(link_id, click_date) DO UPDATE SET click_count = click_count + excluded.click_count
	`)
	if err != nil {
		return err
	}
	defer dailyStmt.Close()

	for linkID, dates := range dailyCounts {
		for date, count := range dates {
			if count > 0 {
				if _, err := dailyStmt.ExecContext(ctx, linkID, date, count); err != nil {
					return err
				}
			}
		}
	}

	// 2. Flush referrers
	refStmt, err := tx.PrepareContext(ctx, `
		INSERT INTO link_referrer_stats (link_id, referrer_host, click_count)
		VALUES (?, ?, ?)
		ON CONFLICT(link_id, referrer_host) DO UPDATE SET click_count = click_count + excluded.click_count
	`)
	if err != nil {
		return err
	}
	defer refStmt.Close()

	for linkID, refs := range referrers {
		for host, count := range refs {
			if count > 0 {
				if _, err := refStmt.ExecContext(ctx, linkID, host, count); err != nil {
					return err
				}
			}
		}
	}

	// 3. Flush devices
	devStmt, err := tx.PrepareContext(ctx, `
		INSERT INTO link_device_stats (link_id, device_family, click_count)
		VALUES (?, ?, ?)
		ON CONFLICT(link_id, device_family) DO UPDATE SET click_count = click_count + excluded.click_count
	`)
	if err != nil {
		return err
	}
	defer devStmt.Close()

	for linkID, devs := range devices {
		for dev, count := range devs {
			if count > 0 {
				if _, err := devStmt.ExecContext(ctx, linkID, dev, count); err != nil {
					return err
				}
			}
		}
	}

	return tx.Commit()
}

func (s *Store) PurgeExpired(ctx context.Context, olderThan time.Time, limit int) (int64, error) {
	cutoff := olderThan.UTC().Format(time.RFC3339Nano)
	query := `
	DELETE FROM links 
	WHERE id IN (
		SELECT id FROM links 
		WHERE expires_at IS NOT NULL AND expires_at < ? 
		LIMIT ?
	)
	`
	res, err := s.db.ExecContext(ctx, query, cutoff, limit)
	if err != nil {
		return 0, err
	}
	return res.RowsAffected()
}

func (s *Store) Ping(ctx context.Context) error {
	return s.db.PingContext(ctx)
}

func (s *Store) Close() error {
	return s.db.Close()
}

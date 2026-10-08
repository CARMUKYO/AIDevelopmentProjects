package postgres

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
	"urlshortener/internal/domain"
)

type Store struct {
	pool *pgxpool.Pool
}

func New(ctx context.Context, connString string) (*Store, error) {
	config, err := pgxpool.ParseConfig(connString)
	if err != nil {
		return nil, fmt.Errorf("invalid postgres connection string: %w", err)
	}

	config.MaxConns = 50
	config.MinConns = 5
	config.MaxConnIdleTime = 5 * time.Minute

	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("unable to connect to postgres: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("postgres ping failed: %w", err)
	}

	return &Store{pool: pool}, nil
}

func (s *Store) CreateLink(ctx context.Context, link *domain.Link) error {
	query := `
	INSERT INTO links (code, original_url, is_custom, delete_token, created_at, expires_at, deleted_at)
	VALUES ($1, $2, $3, $4, $5, $6, $7)
	RETURNING id
	`
	err := s.pool.QueryRow(ctx, query,
		link.Code,
		link.OriginalURL,
		link.IsCustom,
		link.DeleteToken,
		link.CreatedAt.UTC(),
		link.ExpiresAt,
		link.DeletedAt,
	).Scan(&link.ID)

	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" { // unique_violation
			return domain.ErrAliasConflict
		}
		return err
	}

	return nil
}

func (s *Store) GetLinkByCode(ctx context.Context, code string) (*domain.Link, error) {
	query := `
	SELECT id, code, original_url, is_custom, delete_token, created_at, expires_at, deleted_at
	FROM links
	WHERE code = $1
	`
	var l domain.Link
	err := s.pool.QueryRow(ctx, query, code).Scan(
		&l.ID,
		&l.Code,
		&l.OriginalURL,
		&l.IsCustom,
		&l.DeleteToken,
		&l.CreatedAt,
		&l.ExpiresAt,
		&l.DeletedAt,
	)

	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, domain.ErrNotFound
		}
		return nil, err
	}

	l.CreatedAt = l.CreatedAt.UTC()
	if l.ExpiresAt != nil {
		utc := l.ExpiresAt.UTC()
		l.ExpiresAt = &utc
	}
	if l.DeletedAt != nil {
		utc := l.DeletedAt.UTC()
		l.DeletedAt = &utc
	}

	return &l, nil
}

func (s *Store) DeleteLink(ctx context.Context, code string) error {
	query := `
	UPDATE links
	SET deleted_at = (NOW() AT TIME ZONE 'UTC')
	WHERE code = $1 AND deleted_at IS NULL
	`
	cmdTag, err := s.pool.Exec(ctx, query, code)
	if err != nil {
		return err
	}
	if cmdTag.RowsAffected() == 0 {
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
	dailyRows, err := s.pool.Query(ctx, `
		SELECT TO_CHAR(click_date, 'YYYY-MM-DD'), click_count
		FROM link_clicks_daily
		WHERE link_id = $1
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
	refRows, err := s.pool.Query(ctx, `
		SELECT referrer_host, click_count
		FROM link_referrer_stats
		WHERE link_id = $1
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
	devRows, err := s.pool.Query(ctx, `
		SELECT device_family, click_count
		FROM link_device_stats
		WHERE link_id = $1
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
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)

	// 1. Flush daily counts
	dailyQuery := `
		INSERT INTO link_clicks_daily (link_id, click_date, click_count)
		VALUES ($1, $2::date, $3)
		ON CONFLICT (link_id, click_date) DO UPDATE 
		SET click_count = link_clicks_daily.click_count + EXCLUDED.click_count
	`
	for linkID, dates := range dailyCounts {
		for dateStr, count := range dates {
			if count > 0 {
				if _, err := tx.Exec(ctx, dailyQuery, linkID, dateStr, count); err != nil {
					return err
				}
			}
		}
	}

	// 2. Flush referrers
	refQuery := `
		INSERT INTO link_referrer_stats (link_id, referrer_host, click_count)
		VALUES ($1, $2, $3)
		ON CONFLICT (link_id, referrer_host) DO UPDATE 
		SET click_count = link_referrer_stats.click_count + EXCLUDED.click_count
	`
	for linkID, refs := range referrers {
		for host, count := range refs {
			if count > 0 {
				if _, err := tx.Exec(ctx, refQuery, linkID, host, count); err != nil {
					return err
				}
			}
		}
	}

	// 3. Flush devices
	devQuery := `
		INSERT INTO link_device_stats (link_id, device_family, click_count)
		VALUES ($1, $2, $3)
		ON CONFLICT (link_id, device_family) DO UPDATE 
		SET click_count = link_device_stats.click_count + EXCLUDED.click_count
	`
	for linkID, devs := range devices {
		for dev, count := range devs {
			if count > 0 {
				if _, err := tx.Exec(ctx, devQuery, linkID, dev, count); err != nil {
					return err
				}
			}
		}
	}

	return tx.Commit(ctx)
}

func (s *Store) PurgeExpired(ctx context.Context, olderThan time.Time, limit int) (int64, error) {
	query := `
	DELETE FROM links 
	WHERE id IN (
		SELECT id FROM links 
		WHERE expires_at IS NOT NULL AND expires_at < $1 
		LIMIT $2
	)
	`
	tag, err := s.pool.Exec(ctx, query, olderThan.UTC(), limit)
	if err != nil {
		return 0, err
	}
	return tag.RowsAffected(), nil
}

func (s *Store) Ping(ctx context.Context) error {
	return s.pool.Ping(ctx)
}

func (s *Store) Close() error {
	s.pool.Close()
	return nil
}

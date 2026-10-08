package redis

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"github.com/redis/go-redis/v9"
	"urlshortener/internal/domain"
)

type Cache struct {
	client *redis.Client
}

func New(redisURL string) (*Cache, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("invalid redis url: %w", err)
	}

	client := redis.NewClient(opts)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		client.Close()
		return nil, fmt.Errorf("redis ping failed: %w", err)
	}

	return &Cache{client: client}, nil
}

func (c *Cache) Get(ctx context.Context, code string) (*domain.CachedLink, bool, error) {
	key := fmt.Sprintf("link:code:%s", code)
	val, err := c.client.Get(ctx, key).Result()
	if err != nil {
		if errors.Is(err, redis.Nil) {
			return nil, false, nil
		}
		return nil, false, err
	}

	// Check for negative caching sentinel
	if val == "nil" {
		return nil, true, domain.ErrNotFound
	}
	if val == "deleted" {
		return nil, true, domain.ErrDeleted
	}

	var link domain.CachedLink
	if err := json.Unmarshal([]byte(val), &link); err != nil {
		return nil, false, err
	}

	return &link, true, nil
}

func (c *Cache) Set(ctx context.Context, code string, link *domain.CachedLink, ttl time.Duration) error {
	key := fmt.Sprintf("link:code:%s", code)
	var val string

	if link == nil {
		val = "nil"
	} else if link.Deleted {
		val = "deleted"
	} else {
		bytes, err := json.Marshal(link)
		if err != nil {
			return err
		}
		val = string(bytes)
	}

	return c.client.Set(ctx, key, val, ttl).Err()
}

func (c *Cache) Delete(ctx context.Context, code string) error {
	key := fmt.Sprintf("link:code:%s", code)
	// Set deleted sentinel with 1 hour expiration
	return c.client.Set(ctx, key, "deleted", time.Hour).Err()
}

func (c *Cache) RecordClick(ctx context.Context, linkID int64, referrerHost, deviceFamily string) error {
	today := time.Now().UTC().Format("2006-01-02")
	pipe := c.client.Pipeline()

	// 1. Daily clicks hash: buffer:daily:{today} -> field: linkID -> val: count
	pipe.HIncrBy(ctx, fmt.Sprintf("buffer:daily:%s", today), strconv.FormatInt(linkID, 10), 1)

	// 2. Referrer hash: buffer:ref:{linkID} -> field: referrerHost -> val: count
	if referrerHost != "" {
		pipe.HIncrBy(ctx, fmt.Sprintf("buffer:ref:%d", linkID), referrerHost, 1)
	}

	// 3. Device hash: buffer:dev:{linkID} -> field: deviceFamily -> val: count
	if deviceFamily != "" {
		pipe.HIncrBy(ctx, fmt.Sprintf("buffer:dev:%d", linkID), deviceFamily, 1)
	}

	_, err := pipe.Exec(ctx)
	return err
}

func (c *Cache) DrainClicks(ctx context.Context) (dailyCounts map[int64]map[string]int64, referrers map[int64]map[string]int64, devices map[int64]map[string]int64, err error) {
	dailyCounts = make(map[int64]map[string]int64)
	referrers = make(map[int64]map[string]int64)
	devices = make(map[int64]map[string]int64)

	// 1. Drain daily buffers
	dailyKeys, err := c.client.Keys(ctx, "buffer:daily:*").Result()
	if err == nil {
		for _, key := range dailyKeys {
			dateStr := strings.TrimPrefix(key, "buffer:daily:")
			fields, err := c.client.HGetAll(ctx, key).Result()
			if err == nil && len(fields) > 0 {
				c.client.Del(ctx, key)
				for idStr, countStr := range fields {
					linkID, _ := strconv.ParseInt(idStr, 10, 64)
					count, _ := strconv.ParseInt(countStr, 10, 64)
					if linkID > 0 && count > 0 {
						if dailyCounts[linkID] == nil {
							dailyCounts[linkID] = make(map[string]int64)
						}
						dailyCounts[linkID][dateStr] += count
					}
				}
			}
		}
	}

	// 2. Drain referrer buffers
	refKeys, err := c.client.Keys(ctx, "buffer:ref:*").Result()
	if err == nil {
		for _, key := range refKeys {
			idStr := strings.TrimPrefix(key, "buffer:ref:")
			linkID, _ := strconv.ParseInt(idStr, 10, 64)
			fields, err := c.client.HGetAll(ctx, key).Result()
			if err == nil && len(fields) > 0 {
				c.client.Del(ctx, key)
				for host, countStr := range fields {
					count, _ := strconv.ParseInt(countStr, 10, 64)
					if linkID > 0 && count > 0 {
						if referrers[linkID] == nil {
							referrers[linkID] = make(map[string]int64)
						}
						referrers[linkID][host] += count
					}
				}
			}
		}
	}

	// 3. Drain device buffers
	devKeys, err := c.client.Keys(ctx, "buffer:dev:*").Result()
	if err == nil {
		for _, key := range devKeys {
			idStr := strings.TrimPrefix(key, "buffer:dev:")
			linkID, _ := strconv.ParseInt(idStr, 10, 64)
			fields, err := c.client.HGetAll(ctx, key).Result()
			if err == nil && len(fields) > 0 {
				c.client.Del(ctx, key)
				for dev, countStr := range fields {
					count, _ := strconv.ParseInt(countStr, 10, 64)
					if linkID > 0 && count > 0 {
						if devices[linkID] == nil {
							devices[linkID] = make(map[string]int64)
						}
						devices[linkID][dev] += count
					}
				}
			}
		}
	}

	return dailyCounts, referrers, devices, nil
}

func (c *Cache) Ping(ctx context.Context) error {
	return c.client.Ping(ctx).Err()
}

func (c *Cache) Close() error {
	return c.client.Close()
}

package config

import (
	"os"
	"strconv"
)

type Config struct {
	Port              string
	BaseURL           string
	ServerDomain      string
	DBDriver          string // "postgres" or "sqlite"
	DatabaseURL       string
	RedisURL          string // optional, falls back to in-memory cache if empty
	RateLimitPerMin   int
	RateLimitBurst    int
	FlushIntervalSec  int
	CleanerIntervalHr int
}

func Load() *Config {
	port := getEnv("PORT", "8080")
	baseURL := getEnv("BASE_URL", "http://localhost:8080")
	domain := getEnv("SERVER_DOMAIN", "localhost:8080")
	dbDriver := getEnv("DB_DRIVER", "sqlite")
	dbURL := getEnv("DATABASE_URL", "file:urlshortener.db?cache=shared&mode=rwc")
	redisURL := getEnv("REDIS_URL", "")

	rateLimit := getEnvInt("RATE_LIMIT_PER_MIN", 60)
	burst := getEnvInt("RATE_LIMIT_BURST", 10)
	flushSec := getEnvInt("FLUSH_INTERVAL_SEC", 5)
	cleanerHr := getEnvInt("CLEANER_INTERVAL_HR", 24)

	return &Config{
		Port:              port,
		BaseURL:           baseURL,
		ServerDomain:      domain,
		DBDriver:          dbDriver,
		DatabaseURL:       dbURL,
		RedisURL:          redisURL,
		RateLimitPerMin:   rateLimit,
		RateLimitBurst:    burst,
		FlushIntervalSec:  flushSec,
		CleanerIntervalHr: cleanerHr,
	}
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if intVal, err := strconv.Atoi(val); err == nil {
			return intVal
		}
	}
	return defaultVal
}

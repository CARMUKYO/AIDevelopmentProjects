package middleware

import (
	"net/http"
)

const MaxBodyBytes = 16 * 1024 // 16 KB

// LimitBodySize caps incoming HTTP request bodies to 16 KB to protect against memory exhaustion.
func LimitBodySize(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		r.Body = http.MaxBytesReader(w, r.Body, MaxBodyBytes)
		next.ServeHTTP(w, r)
	})
}

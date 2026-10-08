package validator

import (
	"strings"
	"testing"
)

func TestValidateURL(t *testing.T) {
	v := NewValidator("sho.rt")

	tests := []struct {
		name    string
		input   string
		wantErr bool
		errCode string
	}{
		{
			name:    "valid https url",
			input:   "https://example.com/some/path?query=1#hash",
			wantErr: false,
		},
		{
			name:    "valid http url with port",
			input:   "http://example.com:8080/test",
			wantErr: false,
		},
		{
			name:    "valid IDN unicode url",
			input:   "https://münchen.de/events",
			wantErr: false,
		},
		{
			name:    "missing scheme",
			input:   "example.com/path",
			wantErr: true,
			errCode: "INVALID_URL",
		},
		{
			name:    "javascript scheme",
			input:   "javascript:alert(1)",
			wantErr: true,
			errCode: "INVALID_SCHEME",
		},
		{
			name:    "data scheme",
			input:   "data:text/html,<html>Hello</html>",
			wantErr: true,
			errCode: "INVALID_SCHEME",
		},
		{
			name:    "file scheme",
			input:   "file:///etc/passwd",
			wantErr: true,
			errCode: "INVALID_SCHEME",
		},
		{
			name:    "self redirect loop",
			input:   "https://sho.rt/other",
			wantErr: true,
			errCode: "REDIRECT_LOOP",
		},
		{
			name:    "localhost SSRF",
			input:   "http://localhost:3000/admin",
			wantErr: true,
			errCode: "INVALID_URL",
		},
		{
			name:    "127.0.0.1 SSRF",
			input:   "http://127.0.0.1/secrets",
			wantErr: true,
			errCode: "INVALID_URL",
		},
		{
			name:    "AWS metadata SSRF",
			input:   "http://169.254.169.254/latest/meta-data/",
			wantErr: true,
			errCode: "INVALID_URL",
		},
		{
			name:    "Private IP range RFC 1918",
			input:   "http://192.168.1.1/router",
			wantErr: true,
			errCode: "INVALID_URL",
		},
		{
			name:    "Exceeds max length",
			input:   "https://example.com/" + strings.Repeat("a", 2050),
			wantErr: true,
			errCode: "INVALID_URL",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := v.ValidateURL(tt.input)
			if (err != nil) != tt.wantErr {
				t.Fatalf("ValidateURL() err=%v, wantErr=%v (output=%s)", err, tt.wantErr, got)
			}
		})
	}
}

func TestValidateCustomAlias(t *testing.T) {
	v := NewValidator("sho.rt")

	tests := []struct {
		alias   string
		wantErr bool
	}{
		{"my-promo", false},
		{"campaign_2026", false},
		{"api", true},       // reserved
		{"API", true},       // reserved case-insensitive
		{"health", true},    // reserved
		{"Health", true},    // reserved case-insensitive
		{"admin", true},     // reserved
		{"stats", true},     // reserved
		{"ab", true},        // too short
		{"a space", true},   // invalid chars
	}

	for _, tt := range tests {
		t.Run(tt.alias, func(t *testing.T) {
			err := v.ValidateCustomAlias(tt.alias)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateCustomAlias(%q) err=%v, wantErr=%v", tt.alias, err, tt.wantErr)
			}
		})
	}
}

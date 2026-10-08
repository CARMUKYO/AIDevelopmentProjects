package idgen

import (
	"strings"
	"testing"
)

func TestGenerateCode(t *testing.T) {
	gen := NewGenerator()
	codes := make(map[string]bool)

	// Generate 1,000 codes to check length, alphabet, and randomness
	for i := 0; i < 1000; i++ {
		code, err := gen.GenerateCode()
		if err != nil {
			t.Fatalf("unexpected error generating code: %v", err)
		}
		if len(code) != DefaultCodeLen {
			t.Fatalf("expected code length %d, got %d for code %s", DefaultCodeLen, len(code), code)
		}
		for _, c := range code {
			if !strings.ContainsRune(Base62Alphabet, c) {
				t.Fatalf("code %s contains invalid character %c", code, c)
			}
		}
		if codes[code] {
			t.Fatalf("unexpected collision in 1000 codes: %s", code)
		}
		codes[code] = true
	}
}

func TestGenerateDeleteToken(t *testing.T) {
	gen := NewGenerator()
	token, err := gen.GenerateDeleteToken()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(token) != 64 {
		t.Fatalf("expected 64 hex chars, got %d", len(token))
	}
}

func TestValidateAlias(t *testing.T) {
	tests := []struct {
		alias string
		valid bool
	}{
		{"abc", true},
		{"promo-2026", true},
		{"my_link_99", true},
		{"A-Z_0-9", true},
		{"ab", false},                      // too short (< 3)
		{strings.Repeat("a", 33), false},  // too long (> 32)
		{"hello world", false},             // space
		{"promo!", false},                  // punctuation
		{"link@home", false},               // special char
		{"link/path", false},               // slash
	}

	for _, tt := range tests {
		t.Run(tt.alias, func(t *testing.T) {
			err := ValidateAlias(tt.alias)
			if (err == nil) != tt.valid {
				t.Errorf("ValidateAlias(%q) valid=%v, expected=%v, err=%v", tt.alias, err == nil, tt.valid, err)
			}
		})
	}
}

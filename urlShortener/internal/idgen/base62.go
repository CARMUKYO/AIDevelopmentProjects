package idgen

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"math/big"
	"regexp"
)

const (
	// Base62Alphabet contains 62 alphanumeric characters (URL-safe, RFC 3986 unreserved).
	Base62Alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
	DefaultCodeLen = 7
	MinAliasLen    = 3
	MaxAliasLen    = 32
)

var (
	alphabetLen   = big.NewInt(int64(len(Base62Alphabet)))
	aliasRegex    = regexp.MustCompile(`^[a-zA-Z0-9_-]+$`)
	ErrAliasFormat = errors.New("alias must be 3-32 characters and contain only alphanumeric, underscore, or hyphen")
)

// Generator produces cryptographically secure identifiers and tokens.
type Generator struct {
	codeLength int
}

func NewGenerator() *Generator {
	return &Generator{codeLength: DefaultCodeLen}
}

// GenerateCode produces a cryptographically secure random Base62 string of DefaultCodeLen (7 chars).
func (g *Generator) GenerateCode() (string, error) {
	bytes := make([]byte, g.codeLength)
	for i := 0; i < g.codeLength; i++ {
		num, err := rand.Int(rand.Reader, alphabetLen)
		if err != nil {
			return "", err
		}
		bytes[i] = Base62Alphabet[num.Int64()]
	}
	return string(bytes), nil
}

// GenerateDeleteToken creates a 256-bit (32 byte) cryptographically secure hex token (64 chars).
func (g *Generator) GenerateDeleteToken() (string, error) {
	bytes := make([]byte, 32)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return hex.EncodeToString(bytes), nil
}

// ValidateAlias checks if a custom alias satisfies length and charset requirements.
func ValidateAlias(alias string) error {
	l := len(alias)
	if l < MinAliasLen || l > MaxAliasLen {
		return ErrAliasFormat
	}
	if !aliasRegex.MatchString(alias) {
		return ErrAliasFormat
	}
	return nil
}

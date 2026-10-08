package domain

import (
	"errors"
	"fmt"
	"net/http"
)

// AppError represents a domain error with an API error code and HTTP status code.
type AppError struct {
	Code       string        `json:"code"`
	Message    string        `json:"message"`
	HTTPStatus int           `json:"-"`
	Details    []ErrorDetail `json:"details,omitempty"`
}

type ErrorDetail struct {
	Field string `json:"field,omitempty"`
	Issue string `json:"issue"`
}

func (e *AppError) Error() string {
	return fmt.Sprintf("[%s] %s", e.Code, e.Message)
}

// Predefined domain errors
var (
	ErrNotFound = &AppError{
		Code:       "LINK_NOT_FOUND",
		Message:    "The requested short code does not exist.",
		HTTPStatus: http.StatusNotFound,
	}

	ErrExpired = &AppError{
		Code:       "LINK_EXPIRED",
		Message:    "The requested short link has expired.",
		HTTPStatus: http.StatusGone,
	}

	ErrDeleted = &AppError{
		Code:       "LINK_DELETED",
		Message:    "The requested short link has been deleted.",
		HTTPStatus: http.StatusGone,
	}

	ErrAliasConflict = &AppError{
		Code:       "ALIAS_CONFLICT",
		Message:    "The specified custom alias is already in use.",
		HTTPStatus: http.StatusConflict,
	}

	ErrReservedAlias = &AppError{
		Code:       "RESERVED_ALIAS",
		Message:    "The specified alias is a reserved system keyword.",
		HTTPStatus: http.StatusConflict,
	}

	ErrInvalidURL = &AppError{
		Code:       "INVALID_URL",
		Message:    "The destination URL is malformed or invalid.",
		HTTPStatus: http.StatusUnprocessableEntity,
	}

	ErrInvalidScheme = &AppError{
		Code:       "INVALID_SCHEME",
		Message:    "Only http and https URL schemes are permitted.",
		HTTPStatus: http.StatusUnprocessableEntity,
	}

	ErrRedirectLoop = &AppError{
		Code:       "REDIRECT_LOOP",
		Message:    "Target URL points to the shortener service itself.",
		HTTPStatus: http.StatusUnprocessableEntity,
	}

	ErrInvalidExpiration = &AppError{
		Code:       "INVALID_EXPIRATION",
		Message:    "Expiration time must be in the future.",
		HTTPStatus: http.StatusUnprocessableEntity,
	}

	ErrUnauthorized = &AppError{
		Code:       "UNAUTHORIZED",
		Message:    "Invalid or missing management token for this link.",
		HTTPStatus: http.StatusUnauthorized,
	}

	ErrRateLimited = &AppError{
		Code:       "RATE_LIMITED",
		Message:    "Too many requests. Please slow down.",
		HTTPStatus: http.StatusTooManyRequests,
	}

	ErrInternal = &AppError{
		Code:       "INTERNAL_ERROR",
		Message:    "An unexpected error occurred. Please try again later.",
		HTTPStatus: http.StatusInternalServerError,
	}
)

// AsAppError extracts an AppError if present or wraps an unknown error.
func AsAppError(err error) *AppError {
	if err == nil {
		return nil
	}
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr
	}
	return &AppError{
		Code:       "INTERNAL_ERROR",
		Message:    err.Error(),
		HTTPStatus: http.StatusInternalServerError,
	}
}

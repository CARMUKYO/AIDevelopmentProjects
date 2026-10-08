package clock

import "time"

// Clock abstracts time measurement so expiration logic can be tested deterministically
// without sleeping or relying on wall-clock time.
type Clock interface {
	Now() time.Time
}

// RealClock provides actual wall-clock time in UTC.
type RealClock struct{}

func NewRealClock() *RealClock {
	return &RealClock{}
}

func (c *RealClock) Now() time.Time {
	return time.Now().UTC()
}

// MockClock provides a controllable clock for deterministic testing.
type MockClock struct {
	currentTime time.Time
}

func NewMockClock(initial time.Time) *MockClock {
	return &MockClock{currentTime: initial.UTC()}
}

func (m *MockClock) Now() time.Time {
	return m.currentTime
}

func (m *MockClock) Set(t time.Time) {
	m.currentTime = t.UTC()
}

func (m *MockClock) Advance(d time.Duration) {
	m.currentTime = m.currentTime.Add(d)
}

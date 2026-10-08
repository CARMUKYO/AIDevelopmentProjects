#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/userman/Projects/AIDevelopmentProjects/urlShortener"
cd "$PROJECT_DIR"

echo "=== Preparing URL Shortener Demo Environment ==="

# 1. Clean up old demo databases or port 8080 listeners
fuser -k 8080/tcp 2>/dev/null || true
pkill -f "bin/urlshortener" 2>/dev/null || true
rm -f urlshortener.db

# 2. Start the URL Shortener backend server
echo "Starting URL Shortener server on :8080..."
./bin/urlshortener &
SERVER_PID=$!

# Wait for server readiness
echo "Waiting for service to become healthy..."
until curl -s http://localhost:8080/health | grep -q "ok"; do
  sleep 0.2
done
echo "URL Shortener server is running (PID: $SERVER_PID)"

# 3. Start omarchy screen recording
echo "Starting full-screen recording via omarchy..."
omarchy screenrecord --fullscreen

sleep 1.5

# 4. Open Alacritty window and execute the interactive demonstration
echo "Executing demo in Alacritty terminal..."
alacritty --title "URL Shortener - Live Demonstration" -e "$PROJECT_DIR/scripts/run_demo_commands.sh"

# 5. Take high-resolution fullscreen screenshot
echo "Capturing fullscreen screenshot..."
omarchy capture screenshot fullscreen save || true

# 6. Stop omarchy screen recording
echo "Stopping screen recording..."
omarchy screenrecord --stop-recording

# 7. Stop backend server
echo "Stopping URL Shortener server..."
kill -TERM "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true

echo "=== Demo Recording Finished Successfully ==="
ls -lht "$HOME/Videos" | head -5
ls -lht "$HOME/Pictures" | head -5

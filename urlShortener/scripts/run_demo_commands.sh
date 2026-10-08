#!/usr/bin/env bash
set -euo pipefail

# ANSI color codes
BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
RED='\033[0;31m'
RESET='\033[0m'

clear
echo -e "${BOLD}${CYAN}================================================================${RESET}"
echo -e "${BOLD}${CYAN}       🚀 URL SHORTENER SERVICE - PRODUCTION DEMONSTRATION      ${RESET}"
echo -e "${BOLD}${CYAN}================================================================${RESET}"
echo ""
sleep 1

# Step 1: Health Probe
echo -e "${BOLD}${YELLOW}[Step 1] Checking Service Health & Readiness Probe (/health)...${RESET}"
echo -e "${BLUE}$ curl -s http://localhost:8080/health | jq .${RESET}"
curl -s http://localhost:8080/health | jq .
echo ""
sleep 2

# Step 2: Create Custom Alias Link
echo -e "${BOLD}${YELLOW}[Step 2] Creating Short Link with Custom Alias ('mdn-http')...${RESET}"
echo -e "${BLUE}$ curl -s -X POST http://localhost:8080/api/v1/links \\${RESET}"
echo -e "${BLUE}    -H 'Content-Type: application/json' \\${RESET}"
echo -e "${BLUE}    -d '{\"url\":\"https://developer.mozilla.org/en-US/docs/Web/HTTP\",\"alias\":\"mdn-http\"}' | jq .${RESET}"
CREATE_RESP=$(curl -s -X POST http://localhost:8080/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{"url":"https://developer.mozilla.org/en-US/docs/Web/HTTP","alias":"mdn-http"}')
echo "$CREATE_RESP" | jq .
DELETE_TOKEN=$(echo "$CREATE_RESP" | jq -r '.delete_token')
echo ""
sleep 2

# Step 3: Create Auto-Generated Code
echo -e "${BOLD}${YELLOW}[Step 3] Creating Link with Auto-Generated 7-character Base62 Code...${RESET}"
echo -e "${BLUE}$ curl -s -X POST http://localhost:8080/api/v1/links \\${RESET}"
echo -e "${BLUE}    -H 'Content-Type: application/json' \\${RESET}"
echo -e "${BLUE}    -d '{\"url\":\"https://go.dev/doc/effective_go\"}' | jq .${RESET}"
GEN_RESP=$(curl -s -X POST http://localhost:8080/api/v1/links \
  -H "Content-Type: application/json" \
  -d '{"url":"https://go.dev/doc/effective_go"}')
echo "$GEN_RESP" | jq .
GEN_CODE=$(echo "$GEN_RESP" | jq -r '.code')
echo ""
sleep 2

# Step 4: Test HTTP 302 Redirect
echo -e "${BOLD}${YELLOW}[Step 4] Testing Redirect Hot Path (GET /mdn-http)...${RESET}"
echo -e "${BLUE}$ curl -i http://localhost:8080/mdn-http${RESET}"
curl -s -i http://localhost:8080/mdn-http | head -10
echo ""
sleep 2

# Step 5: Simulate Traffic with Diverse Referrers
echo -e "${BOLD}${YELLOW}[Step 5] Simulating Inbound Visits from Twitter, Reddit, and HN...${RESET}"
echo -e "${GREEN}Sending visit from Twitter...${RESET}"
curl -s -H "Referer: https://twitter.com/dev/status/1" http://localhost:8080/mdn-http > /dev/null
echo -e "${GREEN}Sending visit from Reddit...${RESET}"
curl -s -H "Referer: https://reddit.com/r/golang" http://localhost:8080/mdn-http > /dev/null
echo -e "${GREEN}Sending visit from Hacker News...${RESET}"
curl -s -H "Referer: https://news.ycombinator.com" http://localhost:8080/mdn-http > /dev/null
echo -e "${MAGENTA}Waiting for background worker to flush in-memory click batch to DB (5s)...${RESET}"
sleep 5
echo ""

# Step 6: Query Real-Time Statistics
echo -e "${BOLD}${YELLOW}[Step 6] Querying Aggregated Click Statistics (/stats)...${RESET}"
echo -e "${BLUE}$ curl -s http://localhost:8080/api/v1/links/mdn-http/stats | jq .${RESET}"
curl -s http://localhost:8080/api/v1/links/mdn-http/stats | jq .
echo ""
sleep 2

# Step 7: Delete Link with Secret Token
echo -e "${BOLD}${YELLOW}[Step 7] Deleting Link with Secret Token (DELETE /api/v1/links/mdn-http)...${RESET}"
echo -e "${BLUE}$ curl -i -X DELETE http://localhost:8080/api/v1/links/mdn-http -H 'X-Delete-Token: ${DELETE_TOKEN}'${RESET}"
curl -s -i -X DELETE http://localhost:8080/api/v1/links/mdn-http \
  -H "X-Delete-Token: ${DELETE_TOKEN}" | head -5
echo ""
sleep 2

# Step 8: Verify 410 Gone
echo -e "${BOLD}${YELLOW}[Step 8] Verifying Link Returns HTTP 410 Gone Post-Deletion...${RESET}"
echo -e "${BLUE}$ curl -i http://localhost:8080/mdn-http${RESET}"
curl -s -i http://localhost:8080/mdn-http | head -10
echo ""
sleep 2

# Step 9: Verify 404 Not Found for non-existent
echo -e "${BOLD}${YELLOW}[Step 9] Verifying HTTP 404 Not Found for Non-Existent Code...${RESET}"
echo -e "${BLUE}$ curl -i http://localhost:8080/does-not-exist-xyz${RESET}"
curl -s -i http://localhost:8080/does-not-exist-xyz | head -10
echo ""
sleep 2

echo -e "${BOLD}${GREEN}================================================================${RESET}"
echo -e "${BOLD}${GREEN}       ✨ ALL DEMO STEPS COMPLETED SUCCESSFULLY!                ${RESET}"
echo -e "${BOLD}${GREEN}================================================================${RESET}"
sleep 3

#!/usr/bin/env bash
# WorkflowPro — stakeholder demo smoke check + talk track
# Run from repo root: ./scripts/demo_ready.sh

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="${API_URL:-http://localhost:8000}"
WEB="${WEB_URL:-http://localhost:5173}"

green() { printf '\033[32m✓\033[0m %s\n' "$*"; }
red()   { printf '\033[31m✗\033[0m %s\n' "$*"; exit 1; }
info()  { printf '\033[36m→\033[0m %s\n' "$*"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  WorkflowPro — Demo readiness check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1) Backend health
code=$(curl -s -o /tmp/wp_health.json -w "%{http_code}" -m 5 "$API/health" || true)
[[ "$code" == "200" ]] || red "Backend not reachable at $API (got HTTP $code). Start with: cd backend && uvicorn app.main:app --port 8000"
green "Backend liveness ($API/health)"

code=$(curl -s -o /tmp/wp_ready.json -w "%{http_code}" -m 5 "$API/health/ready" || true)
[[ "$code" == "200" || "$code" == "503" ]] || red "Readiness probe failed"
status=$(python3 -c "import json; print(json.load(open('/tmp/wp_ready.json')).get('status','?'))" 2>/dev/null || echo "?")
llm=$(python3 -c "import json; print(json.load(open('/tmp/wp_ready.json')).get('llm_provider','?'))" 2>/dev/null || echo "?")
if [[ "$status" == "ready" ]]; then
  green "Backend readiness (llm=$llm)"
else
  info "Backend degraded (llm=$llm) — Playground AI runs need OPENAI_API_KEY / ANTHROPIC_API_KEY in .env"
fi

# 2) Frontend
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 "$WEB/" || true)
[[ "$code" == "200" ]] || red "Frontend not reachable at $WEB. Start with: cd frontend && npm run dev"
green "Frontend ($WEB)"

# 3) Auth
token=$(curl -s -m 8 -X POST "$API/api/auth/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin@example.com&password=admin123' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
[[ -n "$token" ]] || red "Admin login failed. Run: cd backend && python init_db.py"
green "Admin login works"

# 4) Seed demo data if empty
wf_count=$(curl -s -m 8 -H "Authorization: Bearer $token" "$API/api/workflows/" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null || echo 0)
if [[ "$wf_count" -lt 3 ]]; then
  info "Seeding demo workflows/executions…"
  (cd "$ROOT/backend" && source venv/bin/activate 2>/dev/null; python scripts/seed_demo_data.py --reset)
  green "Demo data seeded"
else
  green "Dashboard data present ($wf_count workflows)"
fi

# 5) Unauthed agent routes stay locked
code=$(curl -s -o /dev/null -w "%{http_code}" -m 5 -X POST "$API/api/automation/run" \
  -H 'Content-Type: application/json' -d '{"query":"test task here"}' || true)
[[ "$code" == "401" ]] || red "Automation endpoint should require auth (got $code)"
green "Automation endpoint is auth-gated (401)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Stakeholder talk track (≈8 minutes)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cat <<EOF

1. Landing   $WEB/
   Brand + one-sentence value: natural language → live browser agent.

2. Login     $WEB/login
   Demo account: admin@example.com / admin123  (leave blank works too)

3. Dashboard $WEB/dashboard
   Stats, recent workflows, activity — looks like a real product.

4. Playground $WEB/playground
   Click "Check HN headlines" → Run Automation
   Show live steps, screenshots, result report (wow moment).

5. Executions $WEB/executions
   History of runs + status filters.

6. Analytics  $WEB/analytics
   Success rate / volume for the funding story.

7. (Optional) Security talking point
   Agent endpoints require JWT; rate-limited login; no shared WS leaks.

EOF
green "Ready for demo. Open $WEB/ and start from the Landing page."
echo ""

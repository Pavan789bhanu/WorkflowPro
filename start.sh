#!/bin/bash
# WorkflowPro — Quick Start
# Starts the FastAPI backend and the Vite frontend dev server.

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

echo "🚀 Starting WorkflowPro…"
echo ""

# ── Environment setup ──────────────────────────────────────────────────────

if [ ! -f "$ROOT/.env" ]; then
    echo "📝 No .env found — creating template at $ROOT/.env"
    cat > "$ROOT/.env" <<'EOF'
# Required
SECRET_KEY=change_me_use_openssl_rand_hex_32

# LLM provider — set at least ONE key. LLM_PROVIDER: auto | openai | anthropic
LLM_PROVIDER=auto
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-sonnet-4-5

# Optional
ENVIRONMENT=development
DEBUG=true
DEFAULT_HEADLESS=true
RATE_LIMIT_PER_MINUTE=60
AGENT_MAX_STEPS=25
AGENT_MAX_CONSECUTIVE_FAILURES=5
EOF
  echo "⚠️  Please edit .env and set SECRET_KEY + an LLM API key (OpenAI or Anthropic), then re-run."
  exit 1
fi

if [ ! -f "$FRONTEND_DIR/.env" ]; then
  if [ -f "$FRONTEND_DIR/.env.example" ]; then
    echo "📝 Creating frontend/.env from .env.example"
    cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env"
  else
    echo "📝 Creating frontend/.env"
    cat > "$FRONTEND_DIR/.env" <<'EOF'
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
EOF
  fi
fi

# ── Python venv + dependencies ─────────────────────────────────────────────

if [ ! -d "$BACKEND_DIR/venv" ]; then
  echo "🐍 Creating Python virtual environment…"
  python3 -m venv "$BACKEND_DIR/venv"
fi

source "$BACKEND_DIR/venv/bin/activate"
echo "📦 Installing Python dependencies…"
pip install -q -r "$BACKEND_DIR/requirements.txt"

echo "🎭 Ensuring Playwright Chromium is installed…"
playwright install chromium --with-deps 2>/dev/null || playwright install chromium

# ── Database ───────────────────────────────────────────────────────────────

echo "🗄️  Initialising database…"
cd "$BACKEND_DIR" && python init_db.py
cd "$ROOT"

# ── Backend ────────────────────────────────────────────────────────────────

echo ""
echo "🔧 Starting backend (port 8000)…"
cd "$BACKEND_DIR"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 > "$ROOT/backend.log" 2>&1 &
BACKEND_PID=$!
cd "$ROOT"
echo "   PID $BACKEND_PID  |  Logs: backend.log"

sleep 3

# ── Frontend ───────────────────────────────────────────────────────────────

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "📦 Installing frontend dependencies…"
  cd "$FRONTEND_DIR" && npm install && cd "$ROOT"
fi

echo "🎨 Starting frontend dev server (port 5173)…"
cd "$FRONTEND_DIR"
npm run dev > "$ROOT/frontend.log" 2>&1 &
FRONTEND_PID=$!
cd "$ROOT"
echo "   PID $FRONTEND_PID  |  Logs: frontend.log"

# ── Save PIDs ──────────────────────────────────────────────────────────────

echo $BACKEND_PID  > "$ROOT/.backend.pid"
echo $FRONTEND_PID > "$ROOT/.frontend.pid"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨  WorkflowPro is running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Frontend  →  http://localhost:5173"
echo "   Backend   →  http://localhost:8000"
echo "   API Docs  →  http://localhost:8000/docs"
echo ""
echo "Default login: admin@example.com / admin123"
echo ""
echo "Logs:  tail -f backend.log frontend.log"
echo "Stop:  ./stop.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

trap "echo ''; echo '🛑 Stopping…'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; rm -f .backend.pid .frontend.pid; echo '✅ Done'; exit 0" INT
wait

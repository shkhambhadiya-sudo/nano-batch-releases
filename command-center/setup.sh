#!/usr/bin/env bash
# One-shot setup for the Mac (M5 Ultra). Idempotent - safe to re-run.
#   ./setup.sh          install deps, build UI, create .env, pull models if Ollama is present
#   ./setup.sh run      ...then start the server in the foreground
#   ./setup.sh install-service   ...and register the launchd service so it starts at login
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }

say "Python environment"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv venv -q .venv
uv pip install -q -e ".[dev]"

say "Frontend"
if ! command -v npm >/dev/null; then
  echo "npm not found. Install Node (https://nodejs.org or 'brew install node') and re-run." >&2; exit 1
fi
(cd frontend && npm install --no-audit --no-fund && npm run build)

say "Config"
if [ ! -f .env ]; then
  cat > .env <<'EOF'
# --- Command Center configuration ---
# Models: "ollama" on the Mac, "mock" to run without a model server.
CC_LLM_BACKEND=ollama
CC_OLLAMA_URL=http://127.0.0.1:11434
CC_MODEL_LARGE=qwen2.5:72b
CC_MODEL_SMALL=qwen2.5:7b
# Integrations: "mock" (fixtures) or "http" (real servers). Read-only in v1.
CC_DEEDS_BACKEND=mock
CC_DEEDS_URL=
CC_DEEDS_TOKEN=
CC_MATRIX_BACKEND=mock
CC_MATRIX_URL=
CC_MATRIX_TOKEN=
# Server
CC_HOST=0.0.0.0
CC_PORT=8787
# Schedules (local time)
CC_ORCHESTRATOR_TIMES=09:00,18:00
CC_VALIDATOR_TIMES=08:30
CC_ANALYST_TIMES=08:00
CC_BRIEF_TIMES=09:15
CC_DOCTOR_INTERVAL_HOURS=6
CC_STALE_DAYS=14
EOF
  echo "wrote .env (edit it to point at 11deeds / 11matrix and your models)"
fi

say "Models"
if command -v ollama >/dev/null; then
  LARGE=$(grep ^CC_MODEL_LARGE .env | cut -d= -f2); SMALL=$(grep ^CC_MODEL_SMALL .env | cut -d= -f2)
  for m in "$SMALL" "$LARGE"; do
    ollama list 2>/dev/null | grep -q "^${m}" || { echo "pulling $m (this can take a while)"; ollama pull "$m"; }
  done
else
  echo "Ollama not installed. Install from https://ollama.com, then re-run ./setup.sh to pull models."
  echo "Until then set CC_LLM_BACKEND=mock in .env to run with rule-based placeholders."
fi

say "Tests"
.venv/bin/python -m pytest -q || { echo "tests failed" >&2; exit 1; }

case "${1:-}" in
  run)
    say "Starting on http://localhost:$(grep ^CC_PORT .env | cut -d= -f2)"
    exec .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port "$(grep ^CC_PORT .env | cut -d= -f2)"
    ;;
  install-service)
    PLIST="$HOME/Library/LaunchAgents/com.commandcenter.server.plist"
    mkdir -p "$HOME/Library/LaunchAgents" logs
    sed "s#__ROOT__#$ROOT#g" launchd/com.commandcenter.server.plist > "$PLIST"
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    say "Service installed: starts at login, restarts on crash. Logs in $ROOT/logs/"
    ;;
  *)
    say "Done. Next: ./setup.sh run   (or ./setup.sh install-service to run at login)"
    ;;
esac

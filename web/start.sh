#!/usr/bin/env bash
# Start Wallet (8002) and TripGo (8003). Wallet starts first to bootstrap issuer artifacts.
set -e
cd "$(dirname "$0")"

if [[ -x .venv/bin/python ]]; then
  PYTHON="${PYTHON:-.venv/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

cleanup() {
  echo
  echo "[stop] killing servers..."
  [[ -n "$WALLET_PID" ]] && kill "$WALLET_PID" 2>/dev/null || true
  [[ -n "$TRIPGO_PID" ]] && kill "$TRIPGO_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[start] wallet on :8002"
$PYTHON wallet_server/app.py 2>&1 | sed 's/^/[wallet] /' &
WALLET_PID=$!

# Wait for wallet to be ready (and to finish bootstrap)
for i in {1..60}; do
  if curl -fs http://127.0.0.1:8002/api/wallet/status >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "[start] tripgo on :8003"
$PYTHON tripgo_server/app.py 2>&1 | sed 's/^/[tripgo] /' &
TRIPGO_PID=$!

for i in {1..30}; do
  if curl -fs http://127.0.0.1:8003/api/catalog >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done

echo
echo "  Wallet  → http://localhost:8002  (Alice 的钱包)"
echo "  TripGo  → http://localhost:8003  (服务商 / 验证者)"
echo
echo "  Ctrl+C to stop."

# Auto-open browsers (macOS / Linux)
if [[ "${OPEN_BROWSER:-1}" == "1" ]]; then
  if command -v open >/dev/null 2>&1; then
    (sleep 0.3; open http://localhost:8002; sleep 0.5; open http://localhost:8003) &
  elif command -v xdg-open >/dev/null 2>&1; then
    (sleep 0.3; xdg-open http://localhost:8002 >/dev/null 2>&1; sleep 0.5; xdg-open http://localhost:8003 >/dev/null 2>&1) &
  fi
fi

wait

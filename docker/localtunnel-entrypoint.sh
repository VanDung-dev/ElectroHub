#!/bin/sh
set -u

# Cài đặt thư viện localtunnel nếu chưa có sẵn trong image
if ! node -e "require('localtunnel')" >/dev/null 2>&1 && ! node -e "require('/usr/local/lib/node_modules/localtunnel')" >/dev/null 2>&1; then
  echo "[localtunnel] Cài đặt thư viện localtunnel..."
  npm install -g localtunnel@2.0.2 --no-fund --no-audit >/dev/null 2>&1 || npm install localtunnel@2.0.2 --no-fund --no-audit >/dev/null 2>&1 || true
fi

# Chạy tunnel controller Node.js làm PID 1 (exec) để đón nhận trực tiếp SIGTERM từ Docker
if [ -f "/app/tunnel.js" ]; then
  exec node /app/tunnel.js
elif [ -f "/app/docker/tunnel.js" ]; then
  exec node /app/docker/tunnel.js
elif [ -f "./docker/tunnel.js" ]; then
  exec node ./docker/tunnel.js
else
  exec node /entrypoint.js
fi

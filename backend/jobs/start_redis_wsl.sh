#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="$project_root/.env"
if [[ ! -f "$env_file" ]]; then
  echo "Project .env file not found: $env_file" >&2
  exit 1
fi

redis_host="$(hostname -I | awk '{print $1}')"
if [[ -z "$redis_host" ]]; then
  echo "Could not determine the WSL network address" >&2
  exit 1
fi

python3 - "$env_file" "$redis_host" <<'PY'
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

env_path = Path(sys.argv[1])
redis_host = sys.argv[2]
lines = env_path.read_text(encoding="utf-8").splitlines()
required = {"REDIS_URL", "CELERY_RESULT_BACKEND"}
found = set()

for index, line in enumerate(lines):
    key, separator, value = line.partition("=")
    if not separator or key.strip() not in required:
        continue
    key = key.strip()
    value = value.strip().strip("\"'")
    parsed = urlsplit(value)
    if parsed.scheme != "redis" or not parsed.password:
        raise SystemExit(f"{key} must be an authenticated redis:// URL")
    username = quote(unquote(parsed.username or ""), safe="")
    password = quote(unquote(parsed.password), safe="")
    auth = f"{username}:{password}@" if username else f":{password}@"
    netloc = f"{auth}{redis_host}:{parsed.port or 6379}"
    lines[index] = f"{key}={urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))}"
    found.add(key)

if found != required:
    raise SystemExit(".env must define REDIS_URL and CELERY_RESULT_BACKEND")

env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

redis_url="$(sed -n 's/^REDIS_URL=//p' "$env_file" | head -n 1)"
redis_password="$(REDIS_URL="$redis_url" python3 -c 'import os; from urllib.parse import unquote, urlsplit; print(unquote(urlsplit(os.environ["REDIS_URL"]).password or ""))')"
if [[ -z "$redis_password" ]]; then
  echo "REDIS_URL must contain a Redis password" >&2
  exit 1
fi

redis_dir="$HOME/.local/share/movie-recommend-redis"
config_dir="$HOME/.config/movierecommend"
mkdir -p "$redis_dir" "$config_dir"
config_file="$config_dir/redis.conf"
umask 077
cat > "$config_file" <<EOF
bind $redis_host
port 6380
protected-mode yes
requirepass $redis_password
daemonize yes
dir $redis_dir
dbfilename dump.rdb
appendonly yes
appendfilename appendonly.aof
pidfile $redis_dir/redis.pid
logfile $redis_dir/redis.log
EOF

if ! REDISCLI_AUTH="$redis_password" redis-cli -h "$redis_host" -p 6380 PING >/dev/null 2>&1; then
  redis-server "$config_file"
fi

REDISCLI_AUTH="$redis_password" redis-cli -h "$redis_host" -p 6380 PING

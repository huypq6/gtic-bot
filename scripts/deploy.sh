#!/usr/bin/env bash
# Deploy gtic-bot to the remote Docker host (default d9020) — build + migrate + verify.
#
#   scripts/deploy.sh                 # checks → tests → DB backup → build → up → verify
#   scripts/deploy.sh --skip-tests    # skip ruff/pytest (still backs up + verifies)
#   scripts/deploy.sh --no-backup     # skip the pre-deploy DB backup
#   scripts/deploy.sh --allow-dirty   # deploy uncommitted changes (version shows "*")
#   scripts/deploy.sh --rollback      # go back to the previous image (no rebuild)
#   scripts/deploy.sh --logs          # follow app logs after deploying
#
# Env overrides: DOCKER_HOST (tcp://d9020:2375), APP_URL (http://d9020:8000), KEEP_BACKUPS (10)
#
# Notes
# - The image is built ON the remote daemon from this working tree (build context is uploaded).
# - `env_file: .env` is read HERE (client side): secrets/keys in THIS machine's .env end up in the
#   container. Edit .env locally, then deploy.
# - The DB container/volume (gtic-bot_pgdata) is never recreated or deleted by this script.
#   Migrations run when the app container starts (alembic upgrade head).
set -euo pipefail

cd "$(dirname "$0")/.."
export DOCKER_HOST="${DOCKER_HOST:-tcp://d9020:2375}"
APP_URL="${APP_URL:-http://d9020:8000}"
PROJECT="gtic-bot"
DB_CT="${PROJECT}-db-1"
APP_IMG="${PROJECT}-app"
KEEP_BACKUPS="${KEEP_BACKUPS:-10}"
COMPOSE=(docker compose -p "$PROJECT" -f docker-compose.yml)

SKIP_TESTS=0 NO_BACKUP=0 ALLOW_DIRTY=0 ROLLBACK=0 FOLLOW=0
for a in "$@"; do
  case "$a" in
    --skip-tests) SKIP_TESTS=1 ;;
    --no-backup) NO_BACKUP=1 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    --rollback) ROLLBACK=1 ;;
    --logs) FOLLOW=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $a (see --help)"; exit 2 ;;
  esac
done

c_ok=$'\033[32m'; c_warn=$'\033[33m'; c_err=$'\033[31m'; c_b=$'\033[1m'; c_0=$'\033[0m'
step() { echo; echo "${c_b}▶ $*${c_0}"; }
ok()   { echo "  ${c_ok}✔${c_0} $*"; }
warn() { echo "  ${c_warn}!${c_0} $*"; }
die()  { echo "  ${c_err}✘ $*${c_0}" >&2; exit 1; }

remote_commit() { curl -fsS -m 5 "$APP_URL/api/version" 2>/dev/null | sed -n 's/.*"commit":"\([^"]*\)".*/\1/p'; }

wait_for() {  # wait_for <expected commit or ""> <timeout s>
  local want="$1" t="$2" got=""
  for ((i = 0; i < t; i += 3)); do
    if curl -fsS -m 3 "$APP_URL/api/health" >/dev/null 2>&1; then
      got="$(remote_commit)"
      if [[ -z "$want" || "$got" == "$want"* ]]; then ok "app healthy at $APP_URL (commit $got)"; return 0; fi
    fi
    sleep 3
  done
  echo "  ${c_err}✘ app not healthy / wrong commit after ${t}s (got '${got:-none}', want '$want')${c_0}"
  echo "  last logs:"; "${COMPOSE[@]}" logs --tail 60 app | sed 's/^/    /'
  echo "  → roll back with: scripts/deploy.sh --rollback"
  return 1
}

# ---------- connectivity ----------
step "Docker host $DOCKER_HOST"
docker version --format '{{.Server.Version}}' >/dev/null 2>&1 || die "cannot reach $DOCKER_HOST"
ok "daemon $(docker version --format '{{.Server.Version}}')"
before="$(remote_commit || true)"
echo "  running now: ${before:-<not running>}"

# ---------- rollback ----------
if ((ROLLBACK)); then
  step "Rollback to the previous image"
  docker image inspect "$APP_IMG:prev" >/dev/null 2>&1 || die "no $APP_IMG:prev image to roll back to"
  docker tag "$APP_IMG:latest" "$APP_IMG:failed" 2>/dev/null || true
  docker tag "$APP_IMG:prev" "$APP_IMG:latest"
  "${COMPOSE[@]}" up -d --no-build app
  wait_for "" 120
  warn "the DB schema is NOT rolled back (migrations only add columns, old code ignores them)."
  warn "to restore data: backups/*.dump → pg_restore (see docs/09 / ask before doing it)."
  exit 0
fi

# ---------- local checks ----------
step "Local checks"
[[ -f .env ]] || die ".env missing — copy env.example to .env and fill it in"
ok ".env present (read here and passed to the container)"
if grep -qE '^ENABLE_LIVE=(1|true|True)' .env; then
  warn "${c_err}ENABLE_LIVE=1 in .env — this deploy UNLOCKS LIVE (real money) mode.${c_0}"
  read -r -p "  type LIVE to continue: " ans
  [[ "$ans" == "LIVE" ]] || die "aborted"
fi
grep -qE '^BINANCE_TESTNET_KEY=.+' .env && ok "testnet key set" || warn "no BINANCE_TESTNET_KEY in .env (TESTNET mode unavailable)"

sha="$(git rev-parse --short HEAD)"
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  ((ALLOW_DIRTY)) || die "uncommitted changes — commit first or use --allow-dirty"
  warn "deploying uncommitted changes on top of $sha"
fi
git fetch -q origin "$branch" 2>/dev/null || true
if [[ -n "$(git log --oneline "origin/$branch..HEAD" 2>/dev/null)" ]]; then
  warn "$branch has commits not pushed to origin"
fi
ok "deploying $branch @ $sha — $(git log -1 --format=%s)"
if [[ -n "$before" && "$before" != "$sha"* ]]; then
  echo "  changes since $before:"
  git log --oneline "$before..HEAD" 2>/dev/null | sed 's/^/    /' || true
  git diff --name-only "$before..HEAD" -- alembic/versions 2>/dev/null | sed 's/^/    migration: /' || true
fi

# ---------- tests ----------
if ((SKIP_TESTS)); then
  warn "tests skipped"
else
  step "Tests"
  uv run ruff check . >/dev/null || die "ruff failed (run: uv run ruff check .)"
  ok "ruff"
  out="$(uv run pytest -q 2>&1 | tail -1)"
  [[ "$out" == *passed* && "$out" != *failed* && "$out" != *error* ]] || die "pytest: $out"
  ok "pytest: $out"
fi

# ---------- backup ----------
if ((NO_BACKUP)); then
  warn "DB backup skipped"
elif docker inspect "$DB_CT" >/dev/null 2>&1; then
  step "DB backup (business data; candles are re-downloadable and excluded)"
  mkdir -p backups
  f="backups/gtic-$(date +%Y%m%d-%H%M%S)-${before:-none}.dump"
  docker exec "$DB_CT" pg_dump -U botuser -d tradingbot -Fc \
    --exclude-table-data=public.kline --exclude-table-data='_timescaledb_internal.*' \
    >"$f" 2>backups/.last-pgdump.log || die "pg_dump failed (see backups/.last-pgdump.log)"
  [[ -s "$f" ]] || die "empty backup $f"
  ok "$f ($(du -h "$f" | cut -f1))"
  ls -1t backups/gtic-*.dump 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | xargs -r rm -f
else
  warn "no $DB_CT container yet — first deploy, nothing to back up"
fi

# ---------- build + up ----------
step "Build image on $DOCKER_HOST"
docker image inspect "$APP_IMG:latest" >/dev/null 2>&1 && docker tag "$APP_IMG:latest" "$APP_IMG:prev"
"${COMPOSE[@]}" build app
ok "built"

step "Start (migrations run on startup)"
"${COMPOSE[@]}" up -d
wait_for "$sha" 180 || exit 1
alembic_v="$(docker exec "$DB_CT" psql -U botuser -d tradingbot -Atc 'select version_num from alembic_version' 2>/dev/null || true)"
ok "DB schema at $alembic_v"
bots="$(curl -fsS -m 5 "$APP_URL/api/bots" | grep -o '"status":"RUNNING"' | wc -l || true)"
ok "$bots bot(s) RUNNING after restart"
echo
echo "${c_ok}${c_b}Deployed $sha → $APP_URL${c_0}   (previous: ${before:-none}; rollback: scripts/deploy.sh --rollback)"

if ((FOLLOW)); then "${COMPOSE[@]}" logs -f --tail 50 app; fi

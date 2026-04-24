#!/usr/bin/env bash
set -euo pipefail

# clear_docker_data.sh — Reset SQLite data inside the Docker volume.
#
# Config:
#   LIFEOS_SERVICE=questlog          docker compose service name
#   LIFEOS_DB=/app/data/web/questlog.db
#   LIFEOS_CLEAR_SCOPE=all|challenge
#
# Examples:
#   scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=challenge scripts/clear_docker_data.sh
#   LIFEOS_SERVICE=questlog scripts/clear_docker_data.sh

cd "$(dirname "$0")/.."

SERVICE="${LIFEOS_SERVICE:-questlog}"
DB="${LIFEOS_DB:-/app/data/web/questlog.db}"
SCOPE="${LIFEOS_CLEAR_SCOPE:-all}"

if [[ "$SCOPE" != "all" && "$SCOPE" != "challenge" ]]; then
  echo "LIFEOS_CLEAR_SCOPE must be 'all' or 'challenge'."
  exit 1
fi

echo "LifeOS Docker Data Reset"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Service: $SERVICE"
echo "Database: $DB"
echo "Scope: $SCOPE"
echo ""
if [[ "$SCOPE" == "challenge" ]]; then
  echo "This will delete Hard 90 challenge data only."
else
  echo "This will delete quests, pomos, trophies, and Hard 90 data."
fi
echo "The SQLite schema, migrations, and sync settings are kept."
echo ""
read -p "Are you sure? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
  echo "Cancelled."
  exit 0
fi

docker compose exec -T "$SERVICE" python - "$DB" "$SCOPE" <<'PYEOF'
import sqlite3
import sys

db_path, scope = sys.argv[1], sys.argv[2]
db = sqlite3.connect(db_path)
db.execute("PRAGMA foreign_keys=OFF")

try:
    db.execute("UPDATE sync_runtime SET value = '1' WHERE key = 'suppress'")
except sqlite3.OperationalError:
    pass

if scope == "challenge":
    tables = ("challenge_entries", "challenge_tasks", "challenge_eras", "challenges")
else:
    tables = (
        "challenge_entries", "challenge_tasks", "challenge_eras", "challenges",
        "pomo_segments", "pomo_sessions", "trophy_records", "quests",
    )

for table in tables:
    try:
        db.execute(f"DELETE FROM {table}")
    except sqlite3.OperationalError as exc:
        print(f"  skip {table}: {exc}")

try:
    placeholders = ",".join("?" * len(tables))
    db.execute(f"DELETE FROM sync_changes WHERE table_name IN ({placeholders})", tables)
    db.execute(f"DELETE FROM sync_conflicts WHERE table_name IN ({placeholders})", tables)
    if scope == "all":
        db.execute("UPDATE sync_state SET value = '' WHERE key IN ('last_pull_at', 'last_push_at', 'last_error')")
        db.execute("UPDATE sync_state SET value = '[]' WHERE key = 'applied_bundles'")
        db.execute("UPDATE sync_state SET value = '0' WHERE key = 'applied_bootstrap'")
finally:
    try:
        db.execute("UPDATE sync_runtime SET value = '0' WHERE key = 'suppress'")
    except sqlite3.OperationalError:
        pass

db.execute("PRAGMA foreign_keys=ON")
db.commit()
db.close()
PYEOF

echo ""
echo "Docker data cleared for scope: $SCOPE"
echo "Refresh the browser, or restart the container if the UI had cached state."

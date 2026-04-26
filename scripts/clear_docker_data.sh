#!/usr/bin/env bash
set -euo pipefail

# clear_docker_data.sh — Reset SQLite data inside the Docker volume.
#
# Config:
#   LIFEOS_SERVICE=questlog          docker compose service name
#   LIFEOS_DB=/app/data/web/questlog.db
#   LIFEOS_CLEAR_SCOPE=questlog|challenge|saga|all
#
# Examples:
#   scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=questlog scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=challenge scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=saga scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=all scripts/clear_docker_data.sh
#   LIFEOS_SERVICE=questlog scripts/clear_docker_data.sh

cd "$(dirname "$0")/.."

SERVICE="${LIFEOS_SERVICE:-questlog}"
DB="${LIFEOS_DB:-/app/data/web/questlog.db}"
SCOPE="${LIFEOS_CLEAR_SCOPE:-}"

if [[ -z "$SCOPE" ]]; then
  echo "LifeOS Docker Data Reset"
  echo "----------------------------------------------------"
  echo ""
  echo "Service: $SERVICE"
  echo "Database: $DB"
  echo ""
  echo "What data do you want to clear?"
  echo "  1) QuestLog      quests, artifacts, pomos, trophies"
  echo "  2) Hard 90       challenges, tasks, entries, eras"
  echo "  3) Saga          emotion log entries"
  echo "  4) All Web Apps  QuestLog, Hard 90, and Saga"
  echo ""
  read -p "Choose 1-4, or q to cancel: " choice
  case "$choice" in
    1) SCOPE="questlog" ;;
    2) SCOPE="challenge" ;;
    3) SCOPE="saga" ;;
    4) SCOPE="all" ;;
    q|Q) echo "Cancelled."; exit 0 ;;
    *) echo "Invalid choice."; exit 1 ;;
  esac
fi

if [[ "$SCOPE" == "quests" ]]; then
  SCOPE="questlog"
fi

if [[ "$SCOPE" != "questlog" && "$SCOPE" != "challenge" && "$SCOPE" != "saga" && "$SCOPE" != "all" ]]; then
  echo "LIFEOS_CLEAR_SCOPE must be 'questlog', 'challenge', 'saga', or 'all'."
  exit 1
fi

echo "LifeOS Docker Data Reset"
echo "----------------------------------------------------"
echo ""
echo "Service: $SERVICE"
echo "Database: $DB"
echo "Scope: $SCOPE"
echo ""
case "$SCOPE" in
  questlog)
    echo "This will delete QuestLog data only:"
    echo "  - Quests"
    echo "  - Artifact keys"
    echo "  - Pomo sessions and segments"
    echo "  - Trophy records"
    ;;
  challenge)
    echo "This will delete Hard 90 challenge data only:"
    echo "  - Challenges"
    echo "  - Challenge tasks"
    echo "  - Daily challenge entries"
    echo "  - Archived challenge eras"
    ;;
  saga)
    echo "This will delete Saga data only:"
    echo "  - Emotion log entries"
    ;;
  all)
    echo "This will delete all LifeOS Web app data:"
    echo "  - QuestLog data"
    echo "  - Hard 90 challenge data"
    echo "  - Saga emotion log data"
    ;;
esac
echo ""
echo "The SQLite schema, migrations, and sync settings are kept."
echo "Sync triggers are suppressed, so this is a local reset and will not queue remote deletes."
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

if scope == "questlog":
    tables = ("pomo_segments", "pomo_sessions", "trophy_records", "artifact_keys", "quests")
elif scope == "challenge":
    tables = ("challenge_entries", "challenge_tasks", "challenge_eras", "challenges")
elif scope == "saga":
    tables = ("saga_entries",)
else:
    tables = (
        "challenge_entries", "challenge_tasks", "challenge_eras", "challenges",
        "pomo_segments", "pomo_sessions", "trophy_records", "artifact_keys", "quests",
        "saga_entries",
    )

counts = {}
for table in tables:
    try:
        counts[table] = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        db.execute(f"DELETE FROM {table}")
    except sqlite3.OperationalError as exc:
        print(f"  skip {table}: {exc}")

try:
    placeholders = ",".join("?" * len(tables))
    db.execute(f"DELETE FROM sync_changes WHERE table_name IN ({placeholders})", tables)
    db.execute(f"DELETE FROM sync_conflicts WHERE table_name IN ({placeholders})", tables)
    db.execute("UPDATE sync_state SET value = '' WHERE key = 'last_error'")
finally:
    try:
        db.execute("UPDATE sync_runtime SET value = '0' WHERE key = 'suppress'")
    except sqlite3.OperationalError:
        pass

db.execute("PRAGMA foreign_keys=ON")
db.commit()
db.close()

for table, count in counts.items():
    print(f"  deleted {count} row(s) from {table}")
PYEOF

echo ""
echo "Docker data cleared for scope: $SCOPE"
echo "Refresh the browser, or restart the container if the UI had cached state."

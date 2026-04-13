#!/usr/bin/env bash
set -euo pipefail

# clear_sql_data.sh — Reset SQLite user data (quests, pomos, trophies)
# Keeps schema and migrations intact.

# Always operate from project root regardless of where script is invoked
cd "$(dirname "$0")/.."

BACKUP_DIR="data/backups"
mkdir -p "$BACKUP_DIR"

DB="${QUESTLOG_DB:-./questlog.db}"

if [[ ! -f "$DB" ]]; then
  echo "No database found at $DB — nothing to clear."
  exit 0
fi

echo "QuestLog SQLite Data Reset"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Database: $DB"
echo ""
echo "This will permanently delete:"
echo "  • All quests"
echo "  • All pomo sessions and segments"
echo "  • All trophy records"
echo ""
read -p "Are you sure? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
  echo "Cancelled."
  exit 0
fi

BACKUP="$BACKUP_DIR/questlog.db.backup.$(date +%Y%m%d-%H%M%S)"
cp "$DB" "$BACKUP"
echo ""
echo "Backup saved: $BACKUP"

python3 - "$DB" <<'PYEOF'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.execute("PRAGMA foreign_keys=OFF")
db.execute("DELETE FROM pomo_segments")
db.execute("DELETE FROM pomo_sessions")
db.execute("DELETE FROM trophy_records")
db.execute("DELETE FROM quests")
db.execute("PRAGMA foreign_keys=ON")
db.commit()
db.close()
PYEOF

echo "Data cleared. Schema and migrations intact."
echo "Restart the app to start fresh."

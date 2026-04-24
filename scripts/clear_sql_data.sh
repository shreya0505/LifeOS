#!/usr/bin/env bash
set -euo pipefail

# clear_sql_data.sh — Reset SQLite user data (quests, pomos, trophies)
# Keeps schema and migrations intact. Backs up first, then optionally
# deletes all backups.

cd "$(dirname "$0")/.."

BACKUP_DIR="data/backups"
mkdir -p "$BACKUP_DIR"

DB="${QUESTLOG_DB:-./data/web/questlog.db}"

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

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_DIR/questlog.db.backup.$TS"
cp "$DB" "$BACKUP"
echo ""
echo "Backup saved: $BACKUP"

python3 - "$DB" <<'PYEOF'
import sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.execute("PRAGMA foreign_keys=OFF")
try:
    db.execute("UPDATE sync_runtime SET value = '1' WHERE key = 'suppress'")
except sqlite3.OperationalError:
    pass
db.execute("DELETE FROM pomo_segments")
db.execute("DELETE FROM pomo_sessions")
db.execute("DELETE FROM trophy_records")
db.execute("DELETE FROM quests")
try:
    db.execute("DELETE FROM sync_changes")
    db.execute("DELETE FROM sync_conflicts")
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

echo "Data cleared. Schema and migrations intact."

# Offer backup deletion
echo ""
EXISTING_BACKUPS=( "$BACKUP_DIR"/questlog.db.backup.* 2>/dev/null ) || true
BACKUP_COUNT=0
for f in "${EXISTING_BACKUPS[@]}"; do [[ -f "$f" ]] && (( BACKUP_COUNT++ )) || true; done

if [[ $BACKUP_COUNT -gt 0 ]]; then
    echo "Found $BACKUP_COUNT DB backup(s) in $BACKUP_DIR/"
    read -p "Delete all DB backups? (yes/no): " del_backups
    if [[ "$del_backups" == "yes" ]]; then
        rm -f "$BACKUP_DIR"/questlog.db.backup.*
        echo "Backups deleted."
    else
        echo "Backups kept."
    fi
fi

echo ""
echo "Restart the app to start fresh."

#!/usr/bin/env bash
set -euo pipefail

# clear_challenge_data.sh — Reset Hard 90 Challenge data only.
# Wipes challenges, challenge_tasks, challenge_entries, challenge_eras.
# Keeps schema, migrations, and all QuestLog/pomo/trophy data intact.
# Backs up the DB first, then optionally deletes all backups.

cd "$(dirname "$0")/.."

BACKUP_DIR="data/backups"
mkdir -p "$BACKUP_DIR"

DB="${QUESTLOG_DB:-./data/web/questlog.db}"

if [[ ! -f "$DB" ]]; then
  echo "No database found at $DB — nothing to clear."
  exit 0
fi

echo "Hard 90 Challenge Data Reset"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Database: $DB"
echo ""
echo "This will permanently delete:"
echo "  • All challenges (active + completed)"
echo "  • All challenge tasks"
echo "  • All challenge entries (daily ratings + notes)"
echo "  • All archived challenge eras"
echo ""
echo "QuestLog quests, pomos, and trophies are NOT touched."
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
for t in ("challenge_entries", "challenge_tasks", "challenge_eras", "challenges"):
    try:
        db.execute(f"DELETE FROM {t}")
    except sqlite3.OperationalError as e:
        print(f"  skip {t}: {e}")
db.execute("PRAGMA foreign_keys=ON")
db.commit()
db.close()
PYEOF

echo "Challenge data cleared. Schema and migrations intact."

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
echo "Restart the app and visit /challenge to set up a fresh era."

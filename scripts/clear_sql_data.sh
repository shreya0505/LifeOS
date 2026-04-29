#!/usr/bin/env bash
set -euo pipefail

# clear_sql_data.sh — Reset QuestLog SQLite data.
# When sync is enabled, this clears local data and restores it from sync.
# Keeps schema and migrations intact. Backs up first, then optionally deletes backups.

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
echo "This will locally delete:"
echo "  • All quests"
echo "  • All artifact keys"
echo "  • All pomo sessions and segments"
echo "  • All trophy records"
echo ""
echo "If sync is enabled:"
echo "  • This will clear local data and restore from sync"
echo "  • This will discard unsynced local changes unless you sync first"
echo "  • This will not delete remote data"
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

DISCARD_ARG=()
read -p "If unsynced local QuestLog changes exist, discard them? (yes/no): " discard_unsynced
if [[ "$discard_unsynced" == "yes" ]]; then
  DISCARD_ARG=(--discard-unsynced)
fi

python3 -m core.maintenance.clear_data --db "$DB" --scope questlog "${DISCARD_ARG[@]}"

echo "Local clear completed. Schema and migrations intact."

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
echo "Restart the app if the UI had cached state."

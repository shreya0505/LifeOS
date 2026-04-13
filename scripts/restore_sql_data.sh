#!/usr/bin/env bash
set -euo pipefail

# restore_sql_data.sh — Restore QuestLog SQLite DB from a backup

cd "$(dirname "$0")/.."

BACKUP_DIR="data/backups"
DB="${QUESTLOG_DB:-./data/web/questlog.db}"

echo "QuestLog SQLite Data Restore"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

DB_BACKUPS=()
for f in "$BACKUP_DIR"/questlog.db.backup.*; do
    [[ -f "$f" ]] && DB_BACKUPS+=("$f")
done

if [[ ${#DB_BACKUPS[@]} -eq 0 ]]; then
    echo "No DB backups found in $BACKUP_DIR/"
    exit 0
fi

echo "Available DB backups:"
for i in "${!DB_BACKUPS[@]}"; do
    echo "  $((i+1))) ${DB_BACKUPS[$i]}"
done
echo ""
read -p "Pick backup number: " pick
idx=$((pick-1))
if [[ $idx -lt 0 || $idx -ge ${#DB_BACKUPS[@]} ]]; then
    echo "Invalid selection."
    exit 1
fi
SRC="${DB_BACKUPS[$idx]}"

echo ""
echo "This will OVERWRITE $DB with $SRC"
read -p "Confirm? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then echo "Cancelled."; exit 0; fi

# Backup current DB before overwrite
if [[ -f "$DB" ]]; then
    PRE="$BACKUP_DIR/questlog.db.backup.pre-restore.$(date +%Y%m%d-%H%M%S)"
    cp "$DB" "$PRE"
    echo "Current DB backed up to: $PRE"
fi

cp "$SRC" "$DB"
echo "Restored: $SRC → $DB"
echo ""
echo "Restart the web app to apply."

#!/usr/bin/env bash
set -euo pipefail

# clear_challenge_data.sh — Reset Hard 90 Challenge data only.
# Wipes challenges, challenge_tasks, challenge_entries, challenge_eras,
# challenge_experiments, and challenge_experiment_entries.
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
echo "This will locally delete:"
echo "  • All tiny experiment protocols and daily signals"
echo "  • All challenges (active + completed)"
echo "  • All challenge tasks"
echo "  • All challenge entries (daily ratings + notes)"
echo "  • All archived challenge eras"
echo ""
echo "QuestLog quests, pomos, and trophies are NOT touched."
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
read -p "If unsynced local Hard 90 changes exist, discard them? (yes/no): " discard_unsynced
if [[ "$discard_unsynced" == "yes" ]]; then
    DISCARD_ARG=(--discard-unsynced)
fi

python3 -m core.maintenance.clear_data --db "$DB" --scope challenge "${DISCARD_ARG[@]}"

echo "Challenge local clear completed. Schema and migrations intact."

echo ""
shopt -s nullglob
EXISTING_BACKUPS=( "$BACKUP_DIR"/questlog.db.backup.* )
shopt -u nullglob
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

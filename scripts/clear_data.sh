#!/usr/bin/env bash
set -euo pipefail

# clear_data.sh — Safely reset QuestLog TUI user data (JSON stores)
#
# Clears quests, pomodoros, trophies. Backs up first, then optionally
# deletes all backups.

cd "$(dirname "$0")/.."

TUI_DATA="data/tui"
BACKUP_DIR="data/backups"
mkdir -p "$TUI_DATA" "$BACKUP_DIR"

echo "QuestLog Data Reset"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "This will permanently delete:"
echo "  • All quests and quest history"
echo "  • All pomodoro sessions and segments"
echo "  • All trophy personal records"
echo ""
read -p "Are you sure? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "Clearing data..."

TS="$(date +%Y%m%d-%H%M%S)"

# Backup before clearing
if [[ -f "$TUI_DATA/quests.json" ]]; then
    cp "$TUI_DATA/quests.json" "$BACKUP_DIR/quests.json.backup.$TS" 2>/dev/null || true
fi
if [[ -f "$TUI_DATA/pomodoros.json" ]]; then
    cp "$TUI_DATA/pomodoros.json" "$BACKUP_DIR/pomodoros.json.backup.$TS" 2>/dev/null || true
fi
if [[ -f "$TUI_DATA/trophies.json" ]]; then
    cp "$TUI_DATA/trophies.json" "$BACKUP_DIR/trophies.json.backup.$TS" 2>/dev/null || true
fi

# Reset to empty state
echo '[]' > "$TUI_DATA/quests.json"
echo '[]' > "$TUI_DATA/pomodoros.json"
echo '{}' > "$TUI_DATA/trophies.json"

echo ""
echo "Data cleared. Backups saved to: $BACKUP_DIR/"

# Offer backup deletion
echo ""
EXISTING_BACKUPS=( "$BACKUP_DIR"/quests.json.backup.* "$BACKUP_DIR"/pomodoros.json.backup.* "$BACKUP_DIR"/trophies.json.backup.* 2>/dev/null ) || true
BACKUP_COUNT=0
for f in "${EXISTING_BACKUPS[@]}"; do [[ -f "$f" ]] && (( BACKUP_COUNT++ )) || true; done

if [[ $BACKUP_COUNT -gt 0 ]]; then
    echo "Found $BACKUP_COUNT JSON backup file(s) in $BACKUP_DIR/"
    read -p "Delete all JSON backups? (yes/no): " del_backups
    if [[ "$del_backups" == "yes" ]]; then
        rm -f "$BACKUP_DIR"/quests.json.backup.* "$BACKUP_DIR"/pomodoros.json.backup.* "$BACKUP_DIR"/trophies.json.backup.*
        echo "Backups deleted."
    else
        echo "Backups kept."
    fi
fi

echo ""
echo "Ready to start fresh — run: python3 -m tui"

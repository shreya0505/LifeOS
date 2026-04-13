#!/usr/bin/env bash
set -euo pipefail

# clear_data.sh — Safely reset QuestLog TUI user data (JSON stores)
#
# This script clears all user data (quests, pomodoros, trophies) and
# reinitializes the app to a fresh state.

# Always operate from project root regardless of where script is invoked
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
echo "Data cleared successfully."
echo ""
echo "Backups saved to: $BACKUP_DIR/"
echo "Ready to start fresh — run: python3 -m tui"

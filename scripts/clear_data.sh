#!/usr/bin/env bash
set -euo pipefail

# clear_data.sh — Safely reset QuestLog TUI user data (JSON stores)
#
# This script clears all user data (quests, pomodoros, trophies) and
# reinitializes the app to a fresh state.

# Always operate from project root regardless of where script is invoked
cd "$(dirname "$0")/.."

BACKUP_DIR="data/backups"
mkdir -p "$BACKUP_DIR"

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
if [[ -f quests.json ]]; then
    cp quests.json "$BACKUP_DIR/quests.json.backup.$TS" 2>/dev/null || true
fi
if [[ -f pomodoros.json ]]; then
    cp pomodoros.json "$BACKUP_DIR/pomodoros.json.backup.$TS" 2>/dev/null || true
fi
if [[ -f trophies.json ]]; then
    cp trophies.json "$BACKUP_DIR/trophies.json.backup.$TS" 2>/dev/null || true
fi

# Reset to empty state
echo '[]' > quests.json
echo '[]' > pomodoros.json
echo '{}' > trophies.json

echo ""
echo "Data cleared successfully."
echo ""
echo "Backups saved to: $BACKUP_DIR/"
echo "Ready to start fresh — run: python3 -m tui"

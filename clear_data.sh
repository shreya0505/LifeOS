#!/usr/bin/env bash
set -euo pipefail

# clear_data.sh — Safely reset QuestLog user data
#
# This script clears all user data (quests, pomodoros, trophies) and
# reinitializes the app to a fresh state.

cd "$(dirname "$0")"

echo "🗑️  QuestLog Data Reset"
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

# Backup before clearing (just in case)
if [[ -f quests.json ]]; then
    cp quests.json "quests.json.backup.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
fi
if [[ -f pomodoros.json ]]; then
    cp pomodoros.json "pomodoros.json.backup.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
fi
if [[ -f trophies.json ]]; then
    cp trophies.json "trophies.json.backup.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
fi

# Reset to empty state
echo '[]' > quests.json
echo '[]' > pomodoros.json
echo '{}' > trophies.json

echo ""
echo "✅ Data cleared successfully."
echo ""
echo "Backup files created with timestamp (if data existed)."
echo "Ready to start fresh — run: python3 main.py"

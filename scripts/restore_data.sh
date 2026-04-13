#!/usr/bin/env bash
set -euo pipefail

# restore_data.sh — Restore QuestLog TUI data (JSON) from a backup

cd "$(dirname "$0")/.."

BACKUP_DIR="data/backups"
TUI_DATA="data/tui"

echo "QuestLog JSON Data Restore"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Collect timestamps from quests backups (all 3 files share same TS)
declare -A JSON_TS_SEEN
for f in "$BACKUP_DIR"/quests.json.backup.*; do
    [[ -f "$f" ]] || continue
    TS="${f##*.backup.}"
    JSON_TS_SEEN["$TS"]=1
done

if [[ ${#JSON_TS_SEEN[@]} -eq 0 ]]; then
    echo "No JSON backups found in $BACKUP_DIR/"
    exit 0
fi

IFS=$'\n' SORTED_TS=($(sort <<<"${!JSON_TS_SEEN[*]}")); unset IFS

echo "Available backup sets:"
for i in "${!SORTED_TS[@]}"; do
    TS="${SORTED_TS[$i]}"
    FILES=""
    [[ -f "$BACKUP_DIR/quests.json.backup.$TS" ]]    && FILES+=" quests"
    [[ -f "$BACKUP_DIR/pomodoros.json.backup.$TS" ]] && FILES+=" pomodoros"
    [[ -f "$BACKUP_DIR/trophies.json.backup.$TS" ]]  && FILES+=" trophies"
    echo "  $((i+1))) $TS —$FILES"
done
echo ""
read -p "Pick backup number: " pick
idx=$((pick-1))
if [[ $idx -lt 0 || $idx -ge ${#SORTED_TS[@]} ]]; then
    echo "Invalid selection."
    exit 1
fi
TS="${SORTED_TS[$idx]}"

echo ""
echo "This will OVERWRITE current TUI data with backup set $TS"
read -p "Confirm? (yes/no): " confirm
if [[ "$confirm" != "yes" ]]; then echo "Cancelled."; exit 0; fi

# Backup current state before overwrite
PRE_TS="pre-restore.$(date +%Y%m%d-%H%M%S)"
for file in quests pomodoros trophies; do
    src="$TUI_DATA/${file}.json"
    [[ -f "$src" ]] && cp "$src" "$BACKUP_DIR/${file}.json.backup.$PRE_TS" || true
done
echo "Current data backed up (timestamp: $PRE_TS)"

# Restore
for file in quests pomodoros trophies; do
    src="$BACKUP_DIR/${file}.json.backup.$TS"
    if [[ -f "$src" ]]; then
        cp "$src" "$TUI_DATA/${file}.json"
        echo "Restored: $src"
    else
        echo "Not found: $src (skipped)"
    fi
done

echo ""
echo "Restore complete. Run: python3 -m tui"

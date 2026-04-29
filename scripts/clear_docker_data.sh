#!/usr/bin/env bash
set -euo pipefail

# clear_docker_data.sh — Reset SQLite data inside the Docker volume.
#
# Config:
#   LIFEOS_SERVICE=questlog          docker compose service name
#   LIFEOS_DB=/app/data/web/questlog.db
#   LIFEOS_CLEAR_SCOPE=questlog|challenge|tiny_experiments|saga|all
#
# Examples:
#   scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=questlog scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=challenge scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=tiny_experiments scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=saga scripts/clear_docker_data.sh
#   LIFEOS_CLEAR_SCOPE=all scripts/clear_docker_data.sh
#   LIFEOS_SERVICE=questlog scripts/clear_docker_data.sh

cd "$(dirname "$0")/.."

SERVICE="${LIFEOS_SERVICE:-questlog}"
DB="${LIFEOS_DB:-/app/data/web/questlog.db}"
SCOPE="${LIFEOS_CLEAR_SCOPE:-}"

if [[ -z "$SCOPE" ]]; then
  echo "LifeOS Docker Data Reset"
  echo "----------------------------------------------------"
  echo ""
  echo "Service: $SERVICE"
  echo "Database: $DB"
  echo ""
  echo "What data do you want to clear?"
  echo "  1) QuestLog      quests, artifacts, pomos, trophies"
  echo "  2) Hard 90       challenges, tasks, entries, eras, tiny experiments"
  echo "  3) Tiny Expts    experiment protocols and daily experiment signals only"
  echo "  4) Saga          emotion log entries"
  echo "  5) All Web Apps  QuestLog, Hard 90, Tiny Experiments, and Saga"
  echo ""
  read -p "Choose 1-5, or q to cancel: " choice
  case "$choice" in
    1) SCOPE="questlog" ;;
    2) SCOPE="challenge" ;;
    3) SCOPE="tiny_experiments" ;;
    4) SCOPE="saga" ;;
    5) SCOPE="all" ;;
    q|Q) echo "Cancelled."; exit 0 ;;
    *) echo "Invalid choice."; exit 1 ;;
  esac
fi

if [[ "$SCOPE" == "quests" ]]; then
  SCOPE="questlog"
fi
if [[ "$SCOPE" == "tiny" || "$SCOPE" == "experiments" || "$SCOPE" == "tiny-experiments" ]]; then
  SCOPE="tiny_experiments"
fi

if [[ "$SCOPE" != "questlog" && "$SCOPE" != "challenge" && "$SCOPE" != "tiny_experiments" && "$SCOPE" != "saga" && "$SCOPE" != "all" ]]; then
  echo "LIFEOS_CLEAR_SCOPE must be 'questlog', 'challenge', 'tiny_experiments', 'saga', or 'all'."
  exit 1
fi

echo "LifeOS Docker Data Reset"
echo "----------------------------------------------------"
echo ""
echo "Service: $SERVICE"
echo "Database: $DB"
echo "Scope: $SCOPE"
echo ""
case "$SCOPE" in
  questlog)
    echo "This will locally delete QuestLog data only:"
    echo "  - Quests"
    echo "  - Artifact keys"
    echo "  - Pomo sessions and segments"
    echo "  - Trophy records"
    ;;
  challenge)
    echo "This will locally delete Hard 90 challenge data only:"
    echo "  - Tiny experiment daily signals"
    echo "  - Tiny experiment protocols"
    echo "  - Challenges"
    echo "  - Challenge tasks"
    echo "  - Daily challenge entries"
    echo "  - Archived challenge eras"
    ;;
  tiny_experiments)
    echo "This will locally delete Tiny Experiments data only:"
    echo "  - Tiny experiment daily signals"
    echo "  - Tiny experiment protocols"
    ;;
  saga)
    echo "This will locally delete Saga data only:"
    echo "  - Emotion log entries"
    ;;
  all)
    echo "This will locally delete all LifeOS Web app data:"
    echo "  - QuestLog data"
    echo "  - Hard 90 challenge data"
    echo "  - Tiny Experiments data"
    echo "  - Saga emotion log data"
    ;;
esac
echo ""
echo "The SQLite schema, migrations, and sync settings are kept."
echo "If sync is enabled:"
echo "  - This will clear local data and restore from sync"
echo "  - This will discard unsynced local changes unless you sync first"
echo "  - This will not delete remote data"
echo ""
read -p "Are you sure? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
  echo "Cancelled."
  exit 0
fi

DISCARD_ARG=()
read -p "If unsynced local changes exist in this scope, discard them? (yes/no): " discard_unsynced
if [[ "$discard_unsynced" == "yes" ]]; then
  DISCARD_ARG=(--discard-unsynced)
fi

docker compose exec -T "$SERVICE" python -m core.maintenance.clear_data --db "$DB" --scope "$SCOPE" "${DISCARD_ARG[@]}"

echo ""
echo "Docker local clear completed for scope: $SCOPE"
echo "Refresh the browser, or restart the container if the UI had cached state."

#!/usr/bin/env bash

SESSION="dev"
PROJECT_DIR="$(pwd)"

# If session exists → attach
tmux has-session -t $SESSION 2>/dev/null
if [ $? -eq 0 ]; then
  tmux attach -t $SESSION
  exit 0
fi

# Create session
tmux new-session -d -s $SESSION -c $PROJECT_DIR
tmux rename-window -t $SESSION:0 'dev'

# --- Pane 0 (top-left) ---
# (empty)

# --- Pane 1 (top-right) ---
tmux split-window -h -t $SESSION:0

# --- Pane 2 (bottom full width) ---
tmux select-pane -t $SESSION:0.0
tmux split-window -v -t $SESSION:0

# --- Resize bottom pane (Claude space) ---
tmux resize-pane -t $SESSION:0.2 -y 20

# Focus bottom pane (optional)
tmux select-pane -t $SESSION:0.2

# Attach
tmux attach -t $SESSION

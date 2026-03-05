#!/bin/bash
# DataChat BI Platform — Environment Setup (idempotent)
# This script runs at the start of each worker session

set -e

PROJECT_ROOT="C:/Users/TF536AC/OneDrive - EY/WORK/ai_engineer_poc_orchestrator"

# Backend: ensure venv exists and dependencies installed
if [ -d "$PROJECT_ROOT/backend/venv" ]; then
  echo "Backend venv exists, checking dependencies..."
  cd "$PROJECT_ROOT/backend"
  venv/Scripts/python.exe -m pip install -r requirements.txt -q 2>/dev/null || true
else
  echo "WARNING: Backend venv not found at $PROJECT_ROOT/backend/venv"
  echo "Create it manually: cd backend && python -m venv venv && venv\\Scripts\\pip install -r requirements.txt"
fi

# Frontend: ensure node_modules exist
if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  cd "$PROJECT_ROOT/frontend"
  npm install
else
  echo "Frontend node_modules exists"
fi

echo "Environment setup complete"

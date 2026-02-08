#!/usr/bin/env bash
set -euo pipefail

# Create dependency virtualenv inside /deps/.venv using `uv` if available,
# otherwise fall back to python -m venv + requirements.txt install.

echo "Creating dependency venv at /deps/.venv"
mkdir -p /deps

if command -v uv >/dev/null 2>&1; then
  echo "uv found, attempting uv sync..."
  if [ -f /app/pyproject.toml ]; then
    uv sync --path /deps/.venv --project /app || true
  elif [ -f /app/requirements.txt ]; then
    python3 -m venv /deps/.venv
    /deps/.venv/bin/pip install --upgrade pip
    /deps/.venv/bin/pip install -r /app/requirements.txt
  else
    python3 -m venv /deps/.venv
    /deps/.venv/bin/pip install --upgrade pip
    echo "No requirements found; created empty venv at /deps/.venv"
  fi
else
  echo "uv not available; using python venv fallback"
  python3 -m venv /deps/.venv
  /deps/.venv/bin/pip install --upgrade pip
  if [ -f /app/requirements.txt ]; then
    /deps/.venv/bin/pip install -r /app/requirements.txt
  fi
fi

echo "Dependency venv ready at /deps/.venv"

# Activate the venv for subsequent initialization steps
export PATH="/deps/.venv/bin:$PATH"
echo "Virtual environment activated"

# Run post-create initialization (database setup, service verification, etc.)
echo ""
echo "Running post-create initialization..."
if [ -x /usr/local/bin/post-create.sh ]; then
  /usr/local/bin/post-create.sh
else
  echo "⚠ post-create.sh not found or not executable; skipping initialization"
  echo "  You may need to manually run: python manage.py migrate"
fi


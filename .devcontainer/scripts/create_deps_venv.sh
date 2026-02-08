#!/usr/bin/env bash
set -euo pipefail

# Create dependency virtualenv inside /deps/.venv using UV package manager.
# UV provides faster, more reliable dependency resolution than pip.
# Falls back to pip-only if UV is not available.

echo "Creating dependency venv at /deps/.venv"
mkdir -p /deps

# Fix any CRLF line endings in global.env that break Django imports
if [ -f /app/global.env ]; then
  sed -i 's/\r$//' /app/global.env
  echo "Line ending conversion completed for global.env"
fi

if command -v uv >/dev/null 2>&1; then
  echo "UV package manager found: $(uv --version)"
  echo "Creating venv with UV..."
  
  uv venv /deps/.venv
  
  # Install from requirements-bootstrap.txt (curated, production-ready deps)
  if [ -f /app/requirements-bootstrap.txt ]; then
    echo "Installing dependencies from requirements-bootstrap.txt..."
    uv pip install --python /deps/.venv/bin/python -r /app/requirements-bootstrap.txt
    echo "✓ UV installation complete"
  else
    # Fallback to requirements.txt if bootstrap not available
    if [ -f /app/requirements.txt ]; then
      echo "requirements-bootstrap.txt not found, falling back to requirements.txt"
      uv pip install --python /deps/.venv/bin/python -r /app/requirements.txt
    else
      echo "⚠ No requirements files found; created empty venv at /deps/.venv"
    fi
  fi
else
  echo "UV not available, using pip-only fallback"
  python3 -m venv /deps/.venv
  /deps/.venv/bin/pip install --upgrade pip
  
  if [ -f /app/requirements-bootstrap.txt ]; then
    echo "Installing from requirements-bootstrap.txt..."
    /deps/.venv/bin/pip install -r /app/requirements-bootstrap.txt
  elif [ -f /app/requirements.txt ]; then
    echo "Installing from requirements.txt..."
    /deps/.venv/bin/pip install -r /app/requirements.txt
  fi
fi

echo "✓ Dependency venv ready at /deps/.venv"

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


#!/usr/bin/env bash
set -euo pipefail

# Create dependency virtualenv inside /deps/.venv using UV package manager.
# UV provides faster, more reliable dependency resolution than pip.
# Falls back to pip-only if UV is not available.

echo "Creating dependency venv at /deps/.venv"
mkdir -p /deps

# Set UV to use copy mode for cross-filesystem compatibility
# Avoids hardlinking warnings when cache and target dirs are on different filesystems
export UV_LINK_MODE=copy

# Fix any CRLF line endings in global.env that break Django imports
if [ -f /app/global.env ]; then
  sed -i 's/\r$//' /app/global.env
  echo "Line ending conversion completed for global.env"
fi

if command -v uv >/dev/null 2>&1; then
  echo "UV package manager found: $(uv --version)"
  
  # IDEMPOTENCE: Check if venv exists and is up-to-date
  REQUIREMENTS_FILE=""
  if [ -f /app/requirements-bootstrap.txt ]; then
    REQUIREMENTS_FILE="/app/requirements-bootstrap.txt"
  elif [ -f /app/requirements.txt ]; then
    REQUIREMENTS_FILE="/app/requirements.txt"
  fi

  SKIP_INSTALL=false
  if [ -f "/deps/.venv/bin/python" ] && [ -n "$REQUIREMENTS_FILE" ]; then
    # Calculate checksum of requirements file
    CURRENT_HASH=$(md5sum "$REQUIREMENTS_FILE" | awk '{print $1}')
    INSTALLED_HASH=""
    
    if [ -f "/deps/.venv/.requirements_hash" ]; then
      INSTALLED_HASH=$(cat "/deps/.venv/.requirements_hash")
    fi
    
    if [ "$CURRENT_HASH" == "$INSTALLED_HASH" ]; then
      echo "✓ Virtual environment is up-to-date (hash match). Skipping installation."
      SKIP_INSTALL=true
    else
      echo "⚠ Requirements changed (hash mismatch). Updating venv..."
    fi
  fi

  if [ "$SKIP_INSTALL" = false ]; then
      echo "Creating/verifying venv with UV..."
      
      # Clean up any stale lock files that might cause hangs
      if [ -f /deps/.venv/.lock ]; then
        echo "Removing stale lock file in /deps/.venv"
        rm -f /deps/.venv/.lock
      fi
      
      uv venv /deps/.venv --allow-existing
      
      if [ -n "$REQUIREMENTS_FILE" ]; then
        echo "Installing dependencies from $(basename $REQUIREMENTS_FILE)..."
        uv pip install --python /deps/.venv/bin/python -r "$REQUIREMENTS_FILE"
        
        # Save the new hash
        md5sum "$REQUIREMENTS_FILE" | awk '{print $1}' > "/deps/.venv/.requirements_hash"
        echo "✓ UV installation complete"
      else
        echo "⚠ No requirements files found; created empty venv at /deps/.venv"
      fi
  fi
else
  echo "UV not available, using pip-only fallback"
  
  # IDEMPOTENCE: Check if venv exists and is up-to-date (Fallback)
  REQUIREMENTS_FILE=""
  if [ -f /app/requirements-bootstrap.txt ]; then
    REQUIREMENTS_FILE="/app/requirements-bootstrap.txt"
  elif [ -f /app/requirements.txt ]; then
    REQUIREMENTS_FILE="/app/requirements.txt"
  fi

  SKIP_INSTALL=false
  if [ -f "/deps/.venv/bin/python" ] && [ -n "$REQUIREMENTS_FILE" ]; then
    # Calculate checksum of requirements file
    CURRENT_HASH=$(md5sum "$REQUIREMENTS_FILE" | awk '{print $1}')
    INSTALLED_HASH=""
    
    if [ -f "/deps/.venv/.requirements_hash" ]; then
      INSTALLED_HASH=$(cat "/deps/.venv/.requirements_hash")
    fi
    
    if [ "$CURRENT_HASH" == "$INSTALLED_HASH" ]; then
      echo "✓ Virtual environment is up-to-date (hash match). Skipping installation."
      SKIP_INSTALL=true
    else
      echo "⚠ Requirements changed (hash mismatch). Updating venv..."
    fi
  fi

  if [ "$SKIP_INSTALL" = false ]; then
      python3 -m venv /deps/.venv
      /deps/.venv/bin/pip install --upgrade pip
      
      if [ -n "$REQUIREMENTS_FILE" ]; then
        echo "Installing from $(basename $REQUIREMENTS_FILE)..."
        /deps/.venv/bin/pip install -r "$REQUIREMENTS_FILE"
        md5sum "$REQUIREMENTS_FILE" | awk '{print $1}' > "/deps/.venv/.requirements_hash"
      fi
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


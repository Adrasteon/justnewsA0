#!/usr/bin/env bash
set -euo pipefail

# Create dependency virtualenv inside /deps/.venv using UV package manager.
# UV provides faster, more reliable dependency resolution than pip.
# Falls back to pip-only if UV is not available.

echo "Creating dependency venv at /deps/.venv"
mkdir -p /deps

# State tracking for conditional summaries
GLOBAL_ENV_NORMALIZED=false
REQUIREMENTS_FILE=""
SKIP_INSTALL=false
USED_UV=false
VENV_CREATED_OR_VERIFIED=false
DEPENDENCIES_INSTALLED=false
EMPTY_VENV_CREATED=false
POST_CREATE_EXECUTED=false
POST_CREATE_SKIPPED=false

# Set UV to use copy mode for cross-filesystem compatibility
# Avoids hardlinking warnings when cache and target dirs are on different filesystems
export UV_LINK_MODE=copy

# Fix any CRLF line endings in global.env that break Django imports
if [ -f /app/global.env ]; then
  sed -i 's/\r$//' /app/global.env
  GLOBAL_ENV_NORMALIZED=true
fi

if command -v uv >/dev/null 2>&1; then
  USED_UV=true
  echo "UV package manager found: $(uv --version)"
  
  # IDEMPOTENCE: Check if venv exists and is up-to-date
  if [ -f /app/requirements-bootstrap.txt ]; then
    REQUIREMENTS_FILE="/app/requirements-bootstrap.txt"
  elif [ -f /app/requirements.txt ]; then
    REQUIREMENTS_FILE="/app/requirements.txt"
  fi

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
      VENV_CREATED_OR_VERIFIED=true
      
      if [ -n "$REQUIREMENTS_FILE" ]; then
        echo "Installing dependencies from $(basename $REQUIREMENTS_FILE)..."
        uv pip install --python /deps/.venv/bin/python -r "$REQUIREMENTS_FILE"
        DEPENDENCIES_INSTALLED=true
        
        # Save the new hash
        md5sum "$REQUIREMENTS_FILE" | awk '{print $1}' > "/deps/.venv/.requirements_hash"
        echo "✓ UV installation complete"
      else
        echo "⚠ No requirements files found; created empty venv at /deps/.venv"
        EMPTY_VENV_CREATED=true
      fi
  fi
else
  echo "UV not available, using pip-only fallback"
  
  # IDEMPOTENCE: Check if venv exists and is up-to-date (Fallback)
  if [ -f /app/requirements-bootstrap.txt ]; then
    REQUIREMENTS_FILE="/app/requirements-bootstrap.txt"
  elif [ -f /app/requirements.txt ]; then
    REQUIREMENTS_FILE="/app/requirements.txt"
  fi

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
      VENV_CREATED_OR_VERIFIED=true
      /deps/.venv/bin/pip install --upgrade pip
      
      if [ -n "$REQUIREMENTS_FILE" ]; then
        echo "Installing from $(basename $REQUIREMENTS_FILE)..."
        /deps/.venv/bin/pip install -r "$REQUIREMENTS_FILE"
        DEPENDENCIES_INSTALLED=true
        md5sum "$REQUIREMENTS_FILE" | awk '{print $1}' > "/deps/.venv/.requirements_hash"
      else
        EMPTY_VENV_CREATED=true
      fi
  fi
fi

if [ "$GLOBAL_ENV_NORMALIZED" = true ]; then
  echo "✓ Normalized line endings in global.env"
fi

if [ "$SKIP_INSTALL" = true ]; then
  echo "✓ Dependency venv unchanged (requirements hash match)"
elif [ "$DEPENDENCIES_INSTALLED" = true ]; then
  if [ "$USED_UV" = true ]; then
    echo "✓ Dependency venv prepared with UV and dependencies installed"
  else
    echo "✓ Dependency venv prepared with pip and dependencies installed"
  fi
elif [ "$VENV_CREATED_OR_VERIFIED" = true ] || [ "$EMPTY_VENV_CREATED" = true ]; then
  echo "✓ Dependency venv prepared (no requirements file detected)"
else
  echo "✓ Dependency venv available at /deps/.venv"
fi

# Activate the venv for subsequent initialization steps
export PATH="/deps/.venv/bin:$PATH"
echo "Virtual environment activated"

# Run post-create initialization (database setup, service verification, etc.)
echo ""
echo "Running post-create initialization..."
if [ -x /usr/local/bin/post-create.sh ]; then
  POST_CREATE_EXECUTED=true
  /usr/local/bin/post-create.sh
else
  POST_CREATE_SKIPPED=true
  echo "⚠ post-create.sh not found or not executable; skipping initialization"
  echo "  You may need to manually run: python manage.py migrate"
fi

if [ "$POST_CREATE_EXECUTED" = true ]; then
  echo "✓ Post-create initialization executed"
elif [ "$POST_CREATE_SKIPPED" = true ]; then
  echo "⚠ Post-create initialization was skipped"
fi


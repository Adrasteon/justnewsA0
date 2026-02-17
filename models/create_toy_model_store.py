#!/usr/bin/env python3
"""Create a small toy ModelStore at /media/adra/Data/justnews/model_store for testing.

This script must be run on the host where the `/media/adra/Data` volume is mounted.
It will create a per-agent directory with a 'current' symlink and a placeholder model file.
"""
import os
from pathlib import Path

BASE = Path(os.environ.get('BASE_MODEL_DIR', '/media/adra/Data/justnews'))
MODEL_STORE = BASE / 'model_store'

def ensure_toy_model(agent='analyst', model_name='sample_model'):
    agent_dir = MODEL_STORE / agent
    version_dir = agent_dir / 'v1'
    model_dir = version_dir / 'models' / model_name
    model_file = model_dir / 'placeholder.txt'
    print('Creating', model_file)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_file.write_text('placeholder model for testing\n')
    # Create/ensure current symlink
    current = agent_dir / 'current'
    if current.exists() or current.is_symlink():
        current.unlink()
    try:
        current.symlink_to(version_dir)
        print('Created current symlink:', current, '->', version_dir)
    except Exception as e:
        print('Failed to create symlink (maybe permissions):', e)

if __name__ == '__main__':
    ensure_toy_model()
    print('Toy ModelStore created at', MODEL_STORE)

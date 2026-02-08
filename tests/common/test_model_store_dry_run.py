"""Dry-run smoke tests for ModelStore-backed loaders."""

from __future__ import annotations

import json
from pathlib import Path

from agents.common import model_loader


def _setup_fake_map(tmp_path: Path, monkeypatch) -> None:
    map_data = {
        "base_models": {
            "mistral-test": {
                "hf_id": "mistralai/Mistral-7B-Instruct-v0.3",
                "model_store_agent": "base_models",
                "model_store_version": "vDryRun",
                "model_store_path": "base_models/versions/vDryRun",
            }
        },
        "agents": {
            "dry_agent": [
                {
                    "base_ref": "mistral-test",
                    "adapter_name": "dry_adapter",
                    "adapter_model_store_path": "dry_agent/adapters/dry_adapter",
                    "variant_preference": "bnb-int8",
                }
            ]
        },
    }
    model_loader._load_agent_model_map.cache_clear()
    monkeypatch.setattr(model_loader, "_load_agent_model_map", lambda: map_data)

    # Ensure directories exist
    version_dir = tmp_path / "base_models/versions/vDryRun"
    version_dir.mkdir(parents=True)
    (tmp_path / "dry_agent/adapters/dry_adapter").mkdir(parents=True)
    manifest_path = version_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"approx_vram_mb": 123}), encoding="utf-8")
    current_link = tmp_path / "base_models/current"
    if current_link.exists() or current_link.is_symlink():
        current_link.unlink()
    current_link.symlink_to(Path("versions/vDryRun"))


def test_dry_run_loader_uses_model_store(monkeypatch, tmp_path):
    _setup_fake_map(tmp_path, monkeypatch)
    monkeypatch.setenv("MODEL_STORE_ROOT", str(tmp_path))
    monkeypatch.setenv("MODEL_STORE_DRY_RUN", "1")

    model, tok = model_loader.load_transformers_with_adapter("dry_agent", "dry_adapter")

    assert model.get("dry_run") is True
    assert tok.get("dry_run") is True
    assert "base_models/versions/vDryRun" in model["base_path"]
    assert tok["adapter_path"].endswith("dry_agent/adapters/dry_adapter")


def test_get_agent_metadata_reads_manifest(monkeypatch, tmp_path):
    _setup_fake_map(tmp_path, monkeypatch)
    monkeypatch.setenv("MODEL_STORE_ROOT", str(tmp_path))

    meta = model_loader.get_agent_model_metadata("dry_agent", "dry_adapter")

    assert meta is not None
    assert meta["manifest"]["approx_vram_mb"] == 123
    assert meta["adapter_path"].exists()

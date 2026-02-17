import json
from datetime import datetime, timedelta
from pathlib import Path

from config.legacy import (
    LegacyConfigFile,
    LegacyConfigurationMigrator,
    MigrationPlan,
    create_legacy_compatibility_layer,
)
from config.schemas import JustNewsConfig


def test_legacyfile_is_active_true_and_false():
    recent = datetime.now()
    old = datetime.now() - timedelta(days=90)

    lf_recent = LegacyConfigFile(
        path=Path("/tmp/recent.json"),
        format="json",
        config_type="database",
        last_modified=recent,
        size_bytes=10,
        content_hash="abc",
    )

    lf_old = LegacyConfigFile(
        path=Path("/tmp/old.json"),
        format="json",
        config_type="database",
        last_modified=old,
        size_bytes=10,
        content_hash="abc",
    )

    assert lf_recent.is_active is True
    assert lf_old.is_active is False


def test_determine_config_type_various_keywords():
    migrator = LegacyConfigurationMigrator()

    assert migrator._determine_config_type(Path("database.json"), "") == "database"
    assert migrator._determine_config_type(Path("gpu.conf"), "") == "gpu"
    assert migrator._determine_config_type(Path("agent_xyz.json"), "") == "agents"
    assert migrator._determine_config_type(Path("crawl_settings.yml"), "") == "crawling"
    assert migrator._determine_config_type(Path("monitor.yaml"), "") == "monitoring"
    assert migrator._determine_config_type(Path("security.env"), "") == "security"
    assert (
        migrator._determine_config_type(Path("training.json"), "train something")
        == "training"
    )
    # Unknown
    assert migrator._determine_config_type(Path("misc.txt"), "nothing relevant") is None


def test_discover_and_load_and_plan(tmp_path, monkeypatch):
    # Change CWD to a temporary folder so discovery does not touch the repo
    monkeypatch.chdir(tmp_path)

    # Create a config directory and a couple of legacy files
    f_db = tmp_path / "database.json"
    f_db.write_text(json.dumps({"host": "localhost", "database": "db1"}))

    f_agent = tmp_path / "agent_config.json"
    f_agent.write_text(json.dumps({"agent": {"enabled": True}}))

    migrator = LegacyConfigurationMigrator()

    discovered = migrator.discover_legacy_configs(search_paths=[tmp_path])
    # We should discover both created files
    assert any(x.path.name == "database.json" for x in discovered)
    assert any("agent" in x.path.name for x in discovered)

    # Ensure load works on one of them
    lf = next(x for x in discovered if x.path.name == "database.json")
    loaded = migrator._load_legacy_config(lf)
    assert loaded["host"] == "localhost"

    # create migration plan
    plan = migrator.create_migration_plan()
    assert isinstance(plan, MigrationPlan)
    # Even with minimal merging, the resulting target_config should be a JustNewsConfig
    assert isinstance(plan.target_config, JustNewsConfig)


def test_generate_compatibility_layer_and_mappings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # Create a stub migration plan that contains steps resulting in key mappings
    plan = MigrationPlan(
        legacy_files=[],
        target_config=JustNewsConfig(),
        migration_steps=[
            "Set system.database.host = localhost",
            "Set system.gpu.enabled = True",
            "Set training.enabled = True",
        ],
        conflicts=[],
        warnings=[],
        estimated_effort="low",
    )

    # Call helper which should write a compatibility file
    compat_path = create_legacy_compatibility_layer(plan)
    assert Path(compat_path).exists()

    content = Path(compat_path).read_text()
    # Ensure our generated mapping keys are present
    assert '"system_database_host": "system.database.host"' in content
    assert '"system_gpu_enabled": "system.gpu.enabled"' in content
    assert '"training_enabled": "training.enabled"' in content

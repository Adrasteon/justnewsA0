import pathlib


def test_adapter_alert_rules_present():
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    rules = repo_root / "docs" / "monitoring" / "adapter-alert-rules.yml"
    assert rules.exists(), f"Alert rules file missing: {rules}"
    content = rules.read_text(encoding="utf-8")
    # Ensure our important alert names exist
    assert "AdapterOpenAIP95High" in content
    assert "AdapterHFP95High" in content
    assert "AdapterErrorRateHigh" in content

import os

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
PROM_CONFIG = os.path.join(REPO_ROOT, "infrastructure/systemd/monitoring/prometheus.yml")


def test_prometheus_config_exists():
    assert os.path.exists(PROM_CONFIG), f"Prometheus config not found: {PROM_CONFIG}"


def test_prometheus_has_rule_files():
    with open(PROM_CONFIG, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    assert "rule_files" in cfg, "prometheus.yml missing 'rule_files' key"
    rule_files = cfg.get("rule_files") or []
    assert isinstance(rule_files, list), "prometheus.yml 'rule_files' must be a list"
    assert len(rule_files) > 0, "prometheus.yml declares no rule files"

    # Check that each referenced rule file exists relative to repo root (common pattern)
    missing = []
    for path in rule_files:
        path = path.strip('"')
        candidate = os.path.join(REPO_ROOT, path)
        if not os.path.exists(candidate):
            missing.append(candidate)
    assert not missing, f"Missing referenced prometheus rule files: {missing}"


def test_mcp_bus_alerts_valid_yaml():
    # Ensure our specific rule file parses and contains groups/rules
    path = os.path.join(REPO_ROOT, "monitoring/alerts/mcp_bus_alerts.yml")
    assert os.path.exists(path), f"mcp_bus alerts file missing: {path}"

    with open(path, encoding="utf-8") as fh:
        parsed = yaml.safe_load(fh)

    assert isinstance(parsed, dict) and "groups" in parsed, "mcp_bus_alerts.yml malformed or missing 'groups'"
    groups = parsed.get("groups") or []
    assert len(groups) > 0, "mcp_bus_alerts.yml contains no groups"

    # Each group should have at least one rule with 'alert' and 'expr'
    found = False
    for g in groups:
        rules = g.get("rules") or []
        for r in rules:
            if r.get("alert") and r.get("expr"):
                found = True
    assert found, "No valid alert rule with 'alert' and 'expr' found in mcp_bus_alerts.yml"

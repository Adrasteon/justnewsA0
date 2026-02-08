import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DASH_JSON = os.path.join(REPO_ROOT, "monitoring/dashboards/generated/system_overview_dashboard.json")


def load_dashboard():
    assert os.path.exists(DASH_JSON), f"Dashboard JSON missing: {DASH_JSON}"
    with open(DASH_JSON, encoding="utf-8") as fh:
        return json.load(fh)


def test_dashboard_parses_json():
    dbl = load_dashboard()
    assert isinstance(dbl, dict), "Dashboard JSON must parse to an object"
    assert "panels" in dbl and isinstance(dbl["panels"], list), "Dashboard missing 'panels' list"


def test_mcp_panels_present():
    dbl = load_dashboard()
    titles = [p.get("title", "") for p in dbl.get("panels", [])]

    assert any("MCP Bus Overall Health" == t for t in titles), "MCP Bus Overall Health panel missing"
    assert any("MCP Bus Agents Degraded Count" == t for t in titles), "MCP Bus Agents Degraded Count panel missing"
    assert any("MCP Bus Agent Status Table" == t for t in titles), "MCP Bus Agent Status Table panel missing"


def test_panel_targets_reference_health_metric():
    dbl = load_dashboard()
    panels = dbl.get("panels", [])
    found_expr = False
    for p in panels:
        targets = p.get("targets", [])
        for t in targets:
            expr = t.get("expr", "")
            if "justnews_agent_health_status" in expr:
                found_expr = True
    assert found_expr, "No panel targets reference 'justnews_agent_health_status' metric"

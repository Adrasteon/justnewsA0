from pathlib import Path


def test_grafana_provisioning_files_exist():
    root = Path(__file__).resolve().parents[2]
    prov = root / "docs" / "grafana" / "provisioning"
    assert prov.exists(), "Grafana provisioning directory missing"
    yaml1 = prov / "dashboards.yml"
    yaml2 = prov / "datasources.yml"
    assert yaml1.exists(), "dashboards.yml missing"
    assert yaml2.exists(), "datasources.yml missing"

    # Check dashboards path is present and dashboard JSON exists
    dashboard_json = root / "docs" / "grafana" / "adapters-dashboard.json"
    assert dashboard_json.exists(), "Grafana dashboard JSON missing"

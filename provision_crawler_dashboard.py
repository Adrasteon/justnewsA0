#!/usr/bin/env python3
"""Provision Crawler & Ingestion Metrics Dashboard to Grafana."""

import json
import subprocess
import sys

GRAFANA_URL = "http://localhost:3000"
GRAFANA_USER = "admin"
GRAFANA_PASSWORD = "admin"
DASHBOARD_FILE = "/home/adra/justnewsA0/monitoring/dashboards/generated/crawler_ingestion_dashboard.json"


def get_grafana_token():
    """Get authentication token from Grafana."""
    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-X",
                "POST",
                f"{GRAFANA_URL}/api/auth/login",
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps({"user": GRAFANA_USER, "password": GRAFANA_PASSWORD}),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("token")
    except Exception as e:
        print(f"Error getting token: {e}")
    return None


def provision_dashboard(token):
    """Upload dashboard to Grafana."""
    try:
        with open(DASHBOARD_FILE) as f:
            dashboard = json.load(f)
        
        payload = {
            "dashboard": dashboard,
            "overwrite": True,
            "message": "Crawler & Ingestion Metrics Dashboard",
        }
        
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-X",
                "POST",
                f"{GRAFANA_URL}/api/dashboards/db",
                "-H",
                "Content-Type: application/json",
                f"-H",
                f"Authorization: Bearer {token}",
                "-d",
                json.dumps(payload),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("id"):
                print(f"✅ Dashboard imported successfully!")
                print(f"   Dashboard ID: {data.get('id')}")
                print(f"   URL: {GRAFANA_URL}{data.get('url', '')}")
                return True
            else:
                print(f"⚠️  Response: {result.stdout[:200]}")
        else:
            print(f"❌ curl error: {result.stderr[:200]}")
    except Exception as e:
        print(f"❌ Error provisioning dashboard: {e}")
    
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("PROVISIONING CRAWLER & INGESTION METRICS DASHBOARD")
    print("=" * 60)
    
    token = get_grafana_token()
    if not token:
        print("❌ Failed to authenticate with Grafana")
        sys.exit(1)
    
    print(f"✅ Got auth token: {token[:20]}...")
    print()
    
    success = provision_dashboard(token)
    
    if not success:
        print("\nNote: Dashboard JSON is saved at:")
        print(f"  {DASHBOARD_FILE}")
        print("\nYou can manually import it from Grafana UI:")
        print(f"  1. Go to {GRAFANA_URL}")
        print("  2. Click '+' → Import dashboard")
        print(f"  3. Upload {DASHBOARD_FILE}")
    
    print("=" * 60)

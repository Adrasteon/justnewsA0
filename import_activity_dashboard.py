import requests
import json
import os

GRAFANA_URL = "http://localhost:3000/api"
AUTH = ("admin", "admin")
DASHBOARD_FILE = "grafana_dashboard_activity.json"

def import_dashboard():
    if not os.path.exists(DASHBOARD_FILE):
        print(f"Error: {DASHBOARD_FILE} not found.")
        return

    with open(DASHBOARD_FILE, 'r') as f:
        dashboard_json = json.load(f)

    # Wrap in the structure Grafana API expects
    payload = {
        "dashboard": dashboard_json,
        "overwrite": True
    }

    url = f"{GRAFANA_URL}/dashboards/db"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    print(f"Importing dashboard from {DASHBOARD_FILE}...")
    try:
        response = requests.post(url, json=payload, auth=AUTH, headers=headers)
        response.raise_for_status()
        result = response.json()
        print("Success!")
        print(f"URL: http://localhost:3000{result.get('url')}")
        print(f"UID: {result.get('uid')}")
    except requests.exceptions.RequestException as e:
        print(f"Error importing dashboard: {e}")
        if hasattr(e, 'response') and e.response is not None:
             print(f"Response: {e.response.text}")

if __name__ == "__main__":
    import_dashboard()

import requests
import json
import pandas as pd

# 1. Section: Load Grafana API Configuration
GRAFANA_URL = "http://localhost:3000/api"
AUTH = ("admin", "admin")  # Replace with appropriate credentials
CORRECT_DATASOURCE_UID = "PBFA97CFB590B2093" # Known good Prometheus UID

def get_grafana_headers():
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

# 2. Section: List All Dashboards
def list_dashboards():
    url = f"{GRAFANA_URL}/search"
    response = requests.get(url, auth=AUTH, headers=get_grafana_headers())
    response.raise_for_status()
    dashboards = response.json()
    print(f"Found {len(dashboards)} dashboards.")
    return [d for d in dashboards if d['type'] == 'dash-db']

dashboards = list_dashboards()
for d in dashboards:
    print(f" - {d['title']} ({d['uid']})")

# 3. Section: Extract Panel Queries from Dashboards
def extract_panel_queries(dashboards):
    all_panels = []
    
    for d in dashboards:
        uid = d['uid']
        url = f"{GRAFANA_URL}/dashboards/uid/{uid}"
        response = requests.get(url, auth=AUTH, headers=get_grafana_headers())
        if response.status_code != 200:
            print(f"Failed to fetch dashboard {uid}")
            continue
            
        dashboard_data = response.json()
        dashboard = dashboard_data['dashboard']
        
        # Helper to process panels (recursive for rows/groups)
        def process_panels(panels_list):
            for panel in panels_list:
                if panel['type'] == 'row' and 'panels' in panel:
                    process_panels(panel['panels'])
                    continue
                
                datasource = panel.get('datasource', {})
                # Handle datasource being a string or dict or None
                ds_uid = None
                if isinstance(datasource, dict):
                    ds_uid = datasource.get('uid')
                elif isinstance(datasource, str):
                    ds_uid = datasource # unlikely in newer grafana but possible
                
                targets = panel.get('targets', [])
                for t in targets:
                    all_panels.append({
                        'dashboard_title': dashboard.get('title'),
                        'dashboard_uid': uid,
                        'panel_title': panel.get('title', 'Untitled'),
                        'panel_id': panel.get('id'),
                        'datasource_uid': ds_uid,
                        'expr': t.get('expr'),
                        'refId': t.get('refId')
                    })

        process_panels(dashboard.get('panels', []))
        
    return pd.DataFrame(all_panels)

df_panels = extract_panel_queries(dashboards)
print(f"Extracted {len(df_panels)} queries")
df_panels.head()

# 4. Section: Test Data Sources Connectivity
def check_datasources():
    url = f"{GRAFANA_URL}/datasources"
    response = requests.get(url, auth=AUTH, headers=get_grafana_headers())
    response.raise_for_status()
    datasources = response.json()
    
    status_report = []
    for ds in datasources:
        # Depending on type, we might want to test connectivity
        # Grafana often has a proxy endpoint /api/datasources/proxy/:id/...
        # or a health check endpoint /api/datasources/:id/health
        
        health_url = f"{GRAFANA_URL}/datasources/{ds['id']}/health"
        health_resp = requests.get(health_url, auth=AUTH, headers=get_grafana_headers())
        
        health_msg = "Unknown"
        if health_resp.status_code == 200:
            health_msg = health_resp.json().get('message', 'OK')
            status = list(health_resp.json().keys())
            if 'status' in health_resp.json() and health_resp.json()['status'] == 'success':
                 is_healthy = True
            else:
                 is_healthy = False
        else:
            is_healthy = False
            health_msg = f"HTTP {health_resp.status_code}"

        status_report.append({
            'name': ds['name'],
            'uid': ds['uid'],
            'type': ds['type'],
            'url': ds['url'],
            'healthy': is_healthy,
            'message': health_msg
        })
        
    return pd.DataFrame(status_report)

df_datasources = check_datasources()
print(df_datasources)

# 5. Section: Update Broken Datasource UIDs
# We found that many dashboards might be using an old or incorrect UID.
# We will check if the datasource UID in the panel matches one of our active healthy datasources.
# If not, and if the type matches (e.g. prometheus), we will update it.

def update_dashboard_datasources(dashboards, correct_prometheus_uid):
    updated_dashboards = []
    
    for d in dashboards:
        uid = d['uid']
        url = f"{GRAFANA_URL}/dashboards/uid/{uid}"
        response = requests.get(url, auth=AUTH, headers=get_grafana_headers())
        if response.status_code != 200:
            continue
            
        dashboard_data = response.json()
        dashboard = dashboard_data['dashboard']
        modified = False
        
        # Recursive update function
        def update_recursive(obj):
            nonlocal modified
            if isinstance(obj, dict):
                # Check for datasource field
                if 'datasource' in obj:
                    ds = obj['datasource']
                    if isinstance(ds, dict):
                        # Logic: If it looks like a prometheus datasource but the UID is wrong/different
                        # OR if the UID is missing but type is prometheus
                        if ds.get('type') == 'prometheus':
                            if ds.get('uid') != correct_prometheus_uid:
                                print(f"[{d['title']}] Updating Prometheus UID from {ds.get('uid')} to {correct_prometheus_uid}")
                                ds['uid'] = correct_prometheus_uid
                                modified = True
                
                # Retrieve panels list if it exists (rows or dashboard root)
                if 'panels' in obj:
                     for panel in obj['panels']:
                        update_recursive(panel)
                
                # Check other keys just in case
                for k, v in obj.items():
                    if k not in ['panels', 'datasource']: 
                        update_recursive(v)
                        
            elif isinstance(obj, list):
                for item in obj:
                    update_recursive(item)
                    
        update_recursive(dashboard)
        
        if modified:
            # Save the dashboard
            save_payload = {
                "dashboard": dashboard,
                "overwrite": True,
                "message": "Updated Datasource UID script"
            }
            save_url = f"{GRAFANA_URL}/dashboards/db"
            resp = requests.post(save_url, auth=AUTH, json=save_payload, headers=get_grafana_headers())
            if resp.status_code == 200:
                updated_dashboards.append(d['title'])
                print(f"Successfully saved {d['title']}")
            else:
                print(f"Failed to save {d['title']}: {resp.text}")

    return updated_dashboards

# Identify the correct Prometheus UID from step 4
# Assuming there is only one Prometheus
prom_ds = df_datasources[df_datasources['type'] == 'prometheus']
if not prom_ds.empty:
    target_uid = prom_ds.iloc[0]['uid']
    print(f"Target Prometheus UID: {target_uid}")
    updated = update_dashboard_datasources(dashboards, target_uid)
    print("Dashboards updated:", updated)
else:
    print("No Prometheus datasource found!")

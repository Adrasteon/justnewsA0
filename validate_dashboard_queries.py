import requests
import json
import re

GRAFANA_URL = "http://localhost:3000/api"
PROMETHEUS_URL = "http://localhost:9090/api/v1"
AUTH = ("admin", "admin")

def get_dashboards():
    resp = requests.get(f"{GRAFANA_URL}/search", auth=AUTH)
    resp.raise_for_status()
    return [d for d in resp.json() if d['type'] == 'dash-db']

def get_dashboard_json(uid):
    resp = requests.get(f"{GRAFANA_URL}/dashboards/uid/{uid}", auth=AUTH)
    resp.raise_for_status()
    return resp.json()['dashboard']

def check_metric_existence(metric_name):
    query = f"present_over_time({metric_name}[1h])" # Check if it existed in last hour
    resp = requests.get(f"{PROMETHEUS_URL}/query", params={"query": query})
    if resp.status_code != 200:
        return False
    data = resp.json()['data']['result']
    return len(data) > 0

def extract_metric_names(expr):
    # Regex to find metric names (simplified: starts with letter, contains alphanumeric or _)
    # Ignores PromQL functions like sum(), rate(), etc.
    # This is a heuristic.
    # Matches words followed by { or just words that look like metrics
    # But valid metric names [a-zA-Z_:][a-zA-Z0-9_:]*
    
    # Strategy: split by non-metric characters and check each candidate
    candidates = re.split(r'[^a-zA-Z0-9_:]', expr)
    metrics = []
    ignorable = {'sum', 'rate', 'irate', 'increase', 'avg', 'min', 'max', 'count', 'by', 'without', 'label_replace', 'histogram_quantile', 'le', 'instance', 'job', 'up'}
    
    for c in candidates:
        if not c: continue
        if c in ignorable: continue
        if c.isdigit(): continue
        if c.startswith('__'): continue
        if c == 'on' or c == 'group_left' or c == 'group_right': continue
        
        # Heuristic: JustNews metrics usually start with "justnews" or "prom" or "go"
        metrics.append(c)
        
    return list(set(metrics))

def main():
    dashboards = get_dashboards()
    print(f"Found {len(dashboards)} dashboards. Validating queries...")
    
    unique_metrics_checked = {} # metric -> exists?
    
    for d in dashboards:
        print(f"\n--- Dashboard: {d['title']} ({d['uid']}) ---")
        dash_json = get_dashboard_json(d['uid'])
        
        panels_to_check = []
        if 'panels' in dash_json:
            panels_to_check.extend(dash_json['panels'])
            
        # flattened list handling rows
        flat_panels = []
        def unroll(panels):
            for p in panels:
                if p['type'] == 'row' and 'panels' in p:
                    unroll(p['panels'])
                else:
                    flat_panels.append(p)
        unroll(panels_to_check)
        
        for p in flat_panels:
            if 'targets' not in p: continue
            
            for t in p['targets']:
                if 'expr' not in t: continue
                expr = t['expr']
                metric_names = extract_metric_names(expr)
                
                missing_metrics = []
                for m in metric_names:
                    if m not in unique_metrics_checked:
                        unique_metrics_checked[m] = check_metric_existence(m)
                    
                    if not unique_metrics_checked[m]:
                        missing_metrics.append(m)
                        
                if missing_metrics:
                    print(f"  [Panel: {p.get('title', 'Unknown')}] Query: {expr}")
                    print(f"    -> MISSING Metrics: {missing_metrics}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

"""
JustNews Grafana Dashboard Provisioning Script (Python)
Purpose: Import all 5 JustNews enterprise dashboards into Grafana
Author: JustNews DevOps
Last Updated: February 3, 2026
"""

import os
import sys
import json
import argparse
import requests
from pathlib import Path
from typing import Optional, Tuple

# Color codes for output
class Colors:
    INFO = '\033[94m'      # Blue
    SUCCESS = '\033[92m'   # Green
    WARNING = '\033[93m'   # Yellow
    ERROR = '\033[91m'     # Red
    RESET = '\033[0m'

def log_info(msg: str):
    print(f"{Colors.INFO}[INFO]{Colors.RESET} {msg}")

def log_success(msg: str):
    print(f"{Colors.SUCCESS}[✓]{Colors.RESET} {msg}")

def log_warning(msg: str):
    print(f"{Colors.WARNING}[⚠]{Colors.RESET} {msg}")

def log_error(msg: str):
    print(f"{Colors.ERROR}[✗]{Colors.RESET} {msg}")

class GrafanaProvisioner:
    """Provision JustNews dashboards into Grafana"""
    
    DASHBOARDS = [
        "system_health_dashboard.json",
        "request_performance_dashboard.json",
        "pipeline_quality_dashboard.json",
        "agent_status_dashboard.json",
        "operational_overview_dashboard.json",
        "crawler_ingestion_dashboard.json",
    ]
    
    DASHBOARD_UIDS = [
        "system-health-premium",
        "request-performance-premium",
        "pipeline-quality-premium",
        "agent-status-premium",
        "operational-overview-premium",
        "crawler-ingestion-metrics",
    ]
    
    def __init__(self, 
                 grafana_url: str = "http://localhost:3000",
                 username: str = "admin",
                 password: str = "admin",
                 verbose: bool = False):
        self.grafana_url = grafana_url.rstrip('/')
        self.username = username
        self.password = password
        self.verbose = verbose
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Determine paths
        script_dir = Path(__file__).parent
        # Go up from infrastructure/monitoring -> infrastructure -> (root)
        project_root = script_dir.parent.parent
        self.dashboards_dir = project_root / "monitoring" / "dashboards" / "generated"
        
    def log_verbose(self, msg: str):
        if self.verbose:
            print(f"{Colors.INFO}[DEBUG]{Colors.RESET} {msg}")
    
    def check_prerequisites(self) -> bool:
        """Check that all prerequisites are met"""
        log_info("Checking prerequisites...")
        
        # Check dashboard directory exists
        if not self.dashboards_dir.exists():
            log_error(f"Dashboards directory not found: {self.dashboards_dir}")
            return False
        
        # Check dashboard files exist
        for dashboard in self.DASHBOARDS:
            dashboard_path = self.dashboards_dir / dashboard
            if not dashboard_path.exists():
                log_error(f"Dashboard file not found: {dashboard_path}")
                return False
        
        log_success("Prerequisites check passed")
        return True
    
    def check_grafana_connection(self) -> bool:
        """Verify Grafana is accessible"""
        log_info("Checking Grafana connectivity...")
        
        try:
            response = self.session.get(f"{self.grafana_url}/api/health")
            if response.status_code == 200:
                log_success(f"Connected to Grafana at {self.grafana_url}")
                return True
            else:
                log_error(f"Cannot connect to Grafana (HTTP {response.status_code})")
                return False
        except Exception as e:
            log_error(f"Cannot connect to Grafana: {str(e)}")
            return False
    
    def get_or_create_datasource(self) -> Optional[int]:
        """Get existing Prometheus datasource or create if not exists"""
        log_info("Checking Prometheus datasource...")
        
        # Try to find existing datasource
        try:
            response = self.session.get(f"{self.grafana_url}/api/datasources/name/Prometheus")
            if response.status_code == 200:
                datasource = response.json()
                log_success(f"Found existing Prometheus datasource (ID: {datasource['id']})")
                return datasource['id']
        except Exception as e:
            self.log_verbose(f"Datasource lookup error: {str(e)}")
        
        # Create new datasource
        log_warning("Prometheus datasource not found, attempting to create...")
        
        try:
            data = {
                "name": "Prometheus",
                "type": "prometheus",
                "url": "http://localhost:9090",
                "access": "proxy",
                "isDefault": True,
                "jsonData": {
                    "timeInterval": "15s"
                }
            }
            response = self.session.post(f"{self.grafana_url}/api/datasources", json=data)
            
            if response.status_code in [200, 201]:
                result = response.json()
                datasource_id = result.get('id')
                log_success(f"Created Prometheus datasource (ID: {datasource_id})")
                return datasource_id
            else:
                log_error(f"Failed to create datasource (HTTP {response.status_code})")
                self.log_verbose(f"Response: {response.text}")
                return None
        except Exception as e:
            log_error(f"Failed to create datasource: {str(e)}")
            return None
    
    def create_dashboard_folder(self) -> Optional[int]:
        """Create or get the JustNews dashboard folder"""
        log_info("Ensuring JustNews dashboard folder exists...")
        
        # Try to find existing folder
        try:
            response = self.session.get(f"{self.grafana_url}/api/folders")
            if response.status_code == 200:
                folders = response.json()
                for folder in folders:
                    if folder.get('title') == 'JustNews':
                        log_success(f"Found existing folder (ID: {folder['id']})")
                        return folder['id']
        except Exception as e:
            self.log_verbose(f"Folder lookup error: {str(e)}")
        
        # Create new folder
        self.log_verbose("Creating JustNews folder...")
        
        try:
            data = {
                "title": "JustNews",
                "description": "JustNews Enterprise Dashboards"
            }
            response = self.session.post(f"{self.grafana_url}/api/folders", json=data)
            
            if response.status_code in [200, 201]:
                result = response.json()
                folder_id = result.get('id')
                log_success(f"Created JustNews folder (ID: {folder_id})")
                return folder_id
            else:
                log_error(f"Failed to create folder (HTTP {response.status_code})")
                self.log_verbose(f"Response: {response.text}")
                return None
        except Exception as e:
            log_error(f"Failed to create folder: {str(e)}")
            return None
    
    def import_dashboard(self, dashboard_file: str, folder_id: int) -> bool:
        """Import a single dashboard"""
        log_info(f"Importing dashboard: {dashboard_file}...")
        
        dashboard_path = self.dashboards_dir / dashboard_file
        
        try:
            # Load dashboard JSON
            with open(dashboard_path, 'r') as f:
                dashboard = json.load(f)
            
            # Prepare import payload
            payload = {
                "dashboard": dashboard,
                "folderId": folder_id,
                "overwrite": True
            }
            
            # Import dashboard
            response = self.session.post(
                f"{self.grafana_url}/api/dashboards/db",
                json=payload
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                dashboard_id = result.get('id')
                dashboard_uid = result.get('uid', 'unknown')
                log_success(f"Imported dashboard (ID: {dashboard_id}, UID: {dashboard_uid})")
                return True
            else:
                log_error(f"Failed to import dashboard (HTTP {response.status_code})")
                self.log_verbose(f"Response: {response.text}")
                return False
        
        except Exception as e:
            log_error(f"Failed to import dashboard: {str(e)}")
            return False
    
    def verify_dashboards(self) -> Tuple[int, int]:
        """Verify all dashboards were imported successfully"""
        log_info("Verifying dashboard imports...")
        
        success_count = 0
        fail_count = 0
        
        for uid in self.DASHBOARD_UIDS:
            try:
                response = self.session.get(f"{self.grafana_url}/api/dashboards/uid/{uid}")
                
                if response.status_code == 200:
                    dashboard = response.json().get('dashboard', {})
                    title = dashboard.get('title', 'Unknown')
                    log_success(f"Verified: {title} (UID: {uid})")
                    success_count += 1
                else:
                    log_warning(f"Not found: {uid}")
                    fail_count += 1
            except Exception as e:
                log_warning(f"Verification error for {uid}: {str(e)}")
                fail_count += 1
        
        log_info(f"Dashboard Verification: {success_count} found, {fail_count} missing")
        return success_count, fail_count
    
    def print_summary(self):
        """Print provisioning summary"""
        print("\n" + "=" * 50)
        print("Dashboard Provisioning Summary")
        print("=" * 50 + "\n")
        print(f"Grafana URL: {self.grafana_url}")
        print(f"Dashboards Directory: {self.dashboards_dir}\n")
        print("Dashboards Provisioned:")
        print("  1. System Health & Infrastructure")
        print("  2. Request Performance & Throughput")
        print("  3. Pipeline Quality & Publishing")
        print("  4. Agent Health & Status")
        print("  5. Operational Overview")
        print("  6. Crawler & Ingestion Metrics\n")
        print("Next Steps:")
        print(f"  1. Access Grafana: {self.grafana_url}")
        print("  2. Go to Dashboards → Browse")
        print("  3. Navigate to the JustNews folder")
        print("  4. Open each dashboard to verify data\n")
        print("Documentation:")
        print("  See ../monitoring/dashboards/DASHBOARD_GUIDE_ENTERPRISE.md")
        print("\n" + "=" * 50 + "\n")
    
    def provision_all(self) -> bool:
        """Run full provisioning workflow"""
        print()
        log_info("JustNews Grafana Dashboard Provisioning Script\n")
        
        # Check prerequisites
        if not self.check_prerequisites():
            return False
        
        # Check Grafana connection
        if not self.check_grafana_connection():
            return False
        
        # Get or create datasource
        datasource_id = self.get_or_create_datasource()
        if datasource_id is None:
            log_warning("Continuing without verifying datasource...")
        
        # Create folder
        folder_id = self.create_dashboard_folder()
        if folder_id is None:
            log_error("Cannot create dashboard folder, aborting")
            return False
        
        # Import dashboards
        success_count = 0
        print()
        for dashboard in self.DASHBOARDS:
            if self.import_dashboard(dashboard, folder_id):
                success_count += 1
        
        print()
        log_info(f"Import complete: {success_count}/{len(self.DASHBOARDS)} dashboards imported")
        
        # Verify imports
        print()
        verified_success, verified_fail = self.verify_dashboards()
        
        # Print summary
        self.print_summary()
        
        # Return success if all imported
        return success_count == len(self.DASHBOARDS) and verified_fail == 0

def main():
    parser = argparse.ArgumentParser(
        description="Provision JustNews dashboards into Grafana"
    )
    parser.add_argument(
        "--grafana-url",
        default="http://localhost:3000",
        help="Grafana base URL (default: %(default)s)"
    )
    parser.add_argument(
        "--grafana-user",
        default="admin",
        help="Grafana username (default: %(default)s)"
    )
    parser.add_argument(
        "--grafana-password",
        default="admin",
        help="Grafana password (default: %(default)s)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    provisioner = GrafanaProvisioner(
        grafana_url=args.grafana_url,
        username=args.grafana_user,
        password=args.grafana_password,
        verbose=args.verbose
    )
    
    success = provisioner.provision_all()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()

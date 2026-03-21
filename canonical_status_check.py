#!/usr/bin/env python3
"""
JustNews Canonical System Status Check
======================================

Rapid "light touch" verification that all JustNews system components are operational.
Designed for quick diagnostics, not replacement for comprehensive testing.

Exit codes:
  0 = GO (all systems operational)
  1 = NO-GO (critical components offline)
  2 = DEGRADED (some services offline but system partially functional)
"""

import subprocess
import sys
import json
import time
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum
import socket
from pathlib import Path

# Optional imports with graceful degradation
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    requests = None

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False
    pymysql = None

try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    chromadb = None

try:
    from chromadb.config import Settings
    HAS_CHROMADB_FULL = True
except ImportError:
    HAS_CHROMADB_FULL = False


class Status(Enum):
    """Service status enumeration."""
    OK = "✓"
    FAIL = "✗"
    WARN = "⚠"
    SKIP = "○"


@dataclass
class CheckResult:
    """Result of a status check."""
    name: str
    status: Status
    duration: float = 0.0
    message: str = ""
    details: Dict = field(default_factory=dict)

    def __str__(self) -> str:
        icon = self.status.value
        msg = f" ({self.message})" if self.message else ""
        dur = f" [{self.duration:.1f}s]" if self.duration > 0 else ""
        return f"{icon} {self.name}{msg}{dur}"


class CanonicalStatusChecker:
    """Main status checking orchestrator."""

    @staticmethod
    def _load_global_env_defaults() -> Dict[str, str]:
        """Load key/value defaults from global.env when present.

        The startup stack treats global.env as canonical. Runtime environment
        variables still override these defaults.
        """
        candidates = [
            Path("/app/global.env"),
            Path.cwd() / "global.env",
        ]
        env_path = next((p for p in candidates if p.exists()), None)
        if env_path is None:
            return {}

        loaded: Dict[str, str] = {}
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                loaded[key] = value.strip().strip('"').strip("'")
        except Exception:
            return {}
        return loaded

    @staticmethod
    def _parse_int(value: Optional[str], default: int) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return default

    def __init__(self, verbose: bool = False):
        """Initialize checker."""
        self.verbose = verbose
        self.results: List[CheckResult] = []
        defaults = self._load_global_env_defaults()
        self.env = os.environ.copy()

        def _cfg(key: str, fallback: str) -> str:
            # Canonical startup uses global.env; prefer it when present.
            if key in defaults and defaults.get(key):
                return str(defaults[key])
            return str(self.env.get(key, fallback))
        
        # Configuration from environment
        self.mariadb_host = _cfg("MARIADB_HOST", "mariadb")
        self.mariadb_port = self._parse_int(_cfg("MARIADB_PORT", "3306"), 3306)
        self.mariadb_user = _cfg("MARIADB_USER", "justnews")
        self.mariadb_password = _cfg("MARIADB_PASSWORD", "dev_justnews_password")
        self.mariadb_db = _cfg("MARIADB_DB", "justnews")
        
        self.chromadb_host = _cfg("CHROMADB_HOST", "chromadb")
        self.chromadb_port = self._parse_int(_cfg("CHROMADB_PORT", "3307"), 3307)
        
        self.vllm_host = _cfg("VLLM_HOST", "vllm")
        self.vllm_port = self._parse_int(_cfg("VLLM_PORT", "8010"), 8010)
        
        self.app_host = _cfg("APP_HOST", "localhost")
        self.app_port = self._parse_int(_cfg("APP_PORT", "8000"), 8000)

    def run_all_checks(self) -> int:
        """Execute all status checks and return exit code."""
        print("\n" + "=" * 60)
        print("JustNews Canonical System Status Check")
        print("=" * 60 + "\n")

        # Phase 1: Infrastructure
        print("📦 INFRASTRUCTURE CHECKS")
        print("-" * 60)
        self.check_docker_containers()
        self.check_port_connectivity()
        print()

        # Phase 2: Services
        print("🔌 SERVICE HEALTH CHECKS")
        print("-" * 60)
        self.check_mariadb_connectivity()
        self.check_chromadb_connectivity()
        self.check_vllm_connectivity()
        print()

        # Phase 3: Database
        print("📊 DATABASE SCHEMA CHECKS")
        print("-" * 60)
        self.check_database_tables()
        self.check_database_migrations()
        print()

        # Phase 4: Vector Database
        print("🧠 VECTOR DATABASE CHECKS")
        print("-" * 60)
        self.check_chromadb_collections()
        print()

        # Phase 5: ML Model
        print("🤖 ML MODEL CHECKS")
        print("-" * 60)
        self.check_vllm_model()
        print()

        # Phase 6: Environment
        print("🔑 ENVIRONMENT CHECKS")
        print("-" * 60)
        self.check_environment_variables()
        self.check_python_dependencies()
        print()

        # Generate summary
        return self.print_summary()

    def record_result(
        self,
        name: str,
        status: Status,
        message: str = "",
        duration: float = 0.0,
    ) -> CheckResult:
        """Record a check result and print it."""
        result = CheckResult(
            name=name,
            status=status,
            message=message,
            duration=duration,
        )
        self.results.append(result)
        print(f"  {result}")
        return result

    # =====================================================================
    # INFRASTRUCTURE CHECKS
    # =====================================================================

    def check_docker_containers(self) -> None:
        """Check if all required Docker containers are running."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=mariadb|chromadb|vllm|app", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            running_containers = set(result.stdout.strip().split("\n")) - {""}
            
            required = {"mariadb", "chromadb", "vllm"}
            missing = required - {c for c in running_containers if any(r in c for r in required)}
            
            if missing:
                self.record_result(
                    "Docker Containers",
                    Status.FAIL,
                    f"Missing: {', '.join(missing)}"
                )
            else:
                self.record_result("Docker Containers", Status.OK)
        except Exception as e:
            self.record_result("Docker Containers", Status.FAIL, str(e))

    def check_port_connectivity(self) -> None:
        """Check if key ports are accessible."""
        ports = [
            ("MariaDB", self.mariadb_host, self.mariadb_port),
            ("ChromaDB", self.chromadb_host, self.chromadb_port),
            ("vLLM", self.vllm_host, self.vllm_port),
        ]
        
        for name, host, port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result == 0:
                    self.record_result(f"Port {name} ({port})", Status.OK)
                else:
                    self.record_result(f"Port {name} ({port})", Status.FAIL, "Connection refused")
            except Exception as e:
                self.record_result(f"Port {name} ({port})", Status.FAIL, str(e)[:40])

    # =====================================================================
    # SERVICE CHECKS
    # =====================================================================

    def check_mariadb_connectivity(self) -> None:
        """Check MariaDB connection and basic query."""
        if not HAS_PYMYSQL:
            self.record_result("MariaDB Connection", Status.SKIP, "pymysql not installed")
            return
            
        start = time.time()
        try:
            conn = pymysql.connect(
                host=self.mariadb_host,
                port=self.mariadb_port,
                user=self.mariadb_user,
                password=self.mariadb_password,
                database=self.mariadb_db,
                connect_timeout=5,
            )
            
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 as test")
                result = cursor.fetchone()
                
            conn.close()
            duration = time.time() - start
            
            if result:
                self.record_result("MariaDB Connection", Status.OK, duration=duration)
            else:
                self.record_result("MariaDB Connection", Status.FAIL, "Query failed")
        except Exception as e:
            self.record_result("MariaDB Connection", Status.FAIL, str(e)[:40])

    def check_chromadb_connectivity(self) -> None:
        """Check ChromaDB HTTP API."""
        if not HAS_REQUESTS:
            self.record_result("ChromaDB API", Status.SKIP, "requests not installed")
            return
            
        start = time.time()
        try:
            url = f"http://{self.chromadb_host}:{self.chromadb_port}/api/v2/heartbeat"
            response = requests.get(url, timeout=5)
            duration = time.time() - start
            
            if response.status_code == 200:
                self.record_result("ChromaDB API", Status.OK, duration=duration)
            else:
                self.record_result(
                    "ChromaDB API",
                    Status.FAIL,
                    f"HTTP {response.status_code}"
                )
        except Exception as e:
            self.record_result("ChromaDB API", Status.FAIL, str(e)[:40])

    def check_vllm_connectivity(self) -> None:
        """Check vLLM API."""
        if not HAS_REQUESTS:
            self.record_result("vLLM API", Status.SKIP, "requests not installed")
            return
            
        start = time.time()
        try:
            url = f"http://{self.vllm_host}:{self.vllm_port}/v1/models"
            response = requests.get(url, timeout=10)
            duration = time.time() - start
            
            if response.status_code == 200:
                self.record_result("vLLM API", Status.OK, duration=duration)
            else:
                self.record_result(
                    "vLLM API",
                    Status.FAIL,
                    f"HTTP {response.status_code}"
                )
        except requests.exceptions.ConnectTimeout:
            self.record_result("vLLM API", Status.FAIL, "Timeout (still loading?)")
        except Exception as e:
            self.record_result("vLLM API", Status.FAIL, str(e)[:40])

    # =====================================================================
    # DATABASE CHECKS
    # =====================================================================

    def check_database_tables(self) -> None:
        """Check if all required tables exist."""
        if not HAS_PYMYSQL:
            self.record_result("Database Tables", Status.SKIP, "pymysql not installed")
            return
            
        required_tables = [
            "publisher_sources",
            "publisher_articles",
            "publisher_keywords",
            "crawler_tasks",
            "crawler_task_articles",
            "crawler_crawl_results",
            "embeddings_collection",
            "embeddings_document",
        ]
        
        try:
            conn = pymysql.connect(
                host=self.mariadb_host,
                port=self.mariadb_port,
                user=self.mariadb_user,
                password=self.mariadb_password,
                database=self.mariadb_db,
                connect_timeout=5,
            )
            
            with conn.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                existing_tables = {row[0] for row in cursor.fetchall()}
            
            conn.close()
            
            missing = set(required_tables) - existing_tables
            found = len(existing_tables)
            
            if missing:
                self.record_result(
                    f"Database Tables ({found} found)",
                    Status.WARN,
                    f"Missing: {', '.join(sorted(missing)[:2])}..."
                )
            else:
                self.record_result(
                    f"Database Tables ({found} found)",
                    Status.OK
                )
        except Exception as e:
            self.record_result("Database Tables", Status.FAIL, str(e)[:40])

    def check_database_migrations(self) -> None:
        """Check if migrations have been applied."""
        if not HAS_PYMYSQL:
            self.record_result("Database Migrations", Status.SKIP, "pymysql not installed")
            return
            
        try:
            conn = pymysql.connect(
                host=self.mariadb_host,
                port=self.mariadb_port,
                user=self.mariadb_user,
                password=self.mariadb_password,
                database=self.mariadb_db,
                connect_timeout=5,
            )
            
            with conn.cursor() as cursor:
                # Check Django migrations
                cursor.execute("SELECT COUNT(*) FROM django_migrations")
                django_count = cursor.fetchone()[0]
                
            conn.close()
            
            if django_count > 0:
                self.record_result(
                    f"Database Migrations ({django_count})",
                    Status.OK
                )
            else:
                self.record_result(
                    "Database Migrations",
                    Status.WARN,
                    "No migrations recorded (may be OK for fresh build)"
                )
        except Exception as e:
            self.record_result("Database Migrations", Status.FAIL, str(e)[:40])

    # =====================================================================
    # VECTOR DATABASE CHECKS
    # =====================================================================

    def check_chromadb_collections(self) -> None:
        """Check ChromaDB collections."""
        try:
            import chromadb as chroma_client
            
            client = chroma_client.HttpClient(
                host=self.chromadb_host,
                port=self.chromadb_port,
            )
            
            collections = client.list_collections()
            collection_count = len(collections)
            
            if collection_count > 0:
                self.record_result(
                    f"ChromaDB Collections ({collection_count})",
                    Status.OK
                )
            else:
                self.record_result(
                    "ChromaDB Collections (0)",
                    Status.WARN,
                    "No collections (expected for fresh build)"
                )
        except ImportError:
            self.record_result("ChromaDB Collections", Status.SKIP, "chromadb not installed")
        except Exception as e:
            # If chromadb is installed but can't connect, that's a service issue
            error_msg = str(e)[:40]
            if "HttpClient" in error_msg or "attribute" in error_msg:
                self.record_result("ChromaDB Collections", Status.SKIP, "chromadb client unavailable")
            else:
                self.record_result("ChromaDB Collections", Status.FAIL, error_msg)

    # =====================================================================
    # ML MODEL CHECKS
    # =====================================================================

    def check_vllm_model(self) -> None:
        """Check if vLLM model is loaded."""
        if not HAS_REQUESTS:
            self.record_result("vLLM Model", Status.SKIP, "requests not installed")
            return
            
        try:
            url = f"http://{self.vllm_host}:{self.vllm_port}/v1/models"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                model_count = len(data.get("data", []))
                
                if model_count > 0:
                    self.record_result(
                        f"vLLM Model ({data['data'][0].get('id', 'unknown')})",
                        Status.OK
                    )
                else:
                    self.record_result(
                        "vLLM Model",
                        Status.WARN,
                        "Model still loading..."
                    )
            else:
                self.record_result("vLLM Model", Status.FAIL, f"HTTP {response.status_code}")
        except requests.exceptions.ConnectTimeout:
            self.record_result("vLLM Model", Status.WARN, "Still initializing (large model)")
        except Exception as e:
            self.record_result("vLLM Model", Status.FAIL, str(e)[:40])

    # =====================================================================
    # ENVIRONMENT CHECKS
    # =====================================================================

    def check_environment_variables(self) -> None:
        """Check critical environment variables."""
        required_vars = [
            "MARIADB_HOST",
            "MARIADB_USER",
            "CHROMADB_HOST",
            "VLLM_HOST",
        ]
        
        missing = [v for v in required_vars if v not in self.env]
        
        if missing:
            self.record_result(
                "Environment Variables",
                Status.WARN,
                f"Missing: {', '.join(missing)}"
            )
        else:
            self.record_result("Environment Variables", Status.OK)

    def check_python_dependencies(self) -> None:
        """Check critical Python packages."""
        required_packages = [
            ("pymysql", HAS_PYMYSQL, "MariaDB connector"),
            ("chromadb", HAS_CHROMADB, "ChromaDB client"),
            ("requests", HAS_REQUESTS, "HTTP client"),
            ("django", True, "Web framework"),  # Check at import time if needed
        ]
        
        missing = []
        for package, has_it, _ in required_packages:
            if not has_it:
                if package != "django":
                    missing.append(package)
                else:
                    try:
                        __import__(package)
                    except ImportError:
                        missing.append(package)
        
        if missing:
            self.record_result(
                "Python Dependencies",
                Status.WARN,
                f"Missing: {', '.join(missing)}"
            )
        else:
            self.record_result("Python Dependencies", Status.OK)

    # =====================================================================
    # SUMMARY
    # =====================================================================

    def print_summary(self) -> int:
        """Print summary and return exit code."""
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60 + "\n")
        
        ok_count = sum(1 for r in self.results if r.status == Status.OK)
        fail_count = sum(1 for r in self.results if r.status == Status.FAIL)
        warn_count = sum(1 for r in self.results if r.status == Status.WARN)
        total_count = len(self.results)
        
        print(f"Checks completed: {total_count}")
        print(f"  ✓ OK:       {ok_count}")
        print(f"  ⚠ Warnings: {warn_count}")
        print(f"  ✗ Failures: {fail_count}")
        print()
        
        # Determine status
        if fail_count == 0 and warn_count == 0:
            status = "🟢 GO"
            exit_code = 0
        elif fail_count == 0:
            status = "🟡 GO (with warnings)"
            exit_code = 0
        elif fail_count <= 2:
            status = "🟠 DEGRADED"
            exit_code = 2
        else:
            status = "🔴 NO-GO"
            exit_code = 1
        
        print(f"System Status: {status}")
        print()
        
        if fail_count > 0:
            print("Failed checks (needs attention):")
            for result in self.results:
                if result.status == Status.FAIL:
                    print(f"  • {result.name}: {result.message}")
            print()
        
        if warn_count > 0:
            print("Warnings (may be expected):")
            for result in self.results:
                if result.status == Status.WARN:
                    print(f"  • {result.name}: {result.message}")
            print()
        
        return exit_code


def main():
    """Entry point."""
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    try:
        checker = CanonicalStatusChecker(verbose=verbose)
        exit_code = checker.run_all_checks()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

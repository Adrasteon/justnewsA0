import subprocess
import time

import pytest
import requests

DEV_COMPOSE = "infrastructure/monitoring/dev-docker-compose.yaml"


def docker_available():
    try:
        subprocess.run(["docker", "ps"], capture_output=True, check=True)
        subprocess.run(
            ["docker", "compose", "version"], capture_output=True, check=True
        )
        return True
    except Exception:
        return False


@pytest.mark.skipif(not docker_available(), reason="docker not available")
def test_dev_telemetry_stack_smoke():
    """Smoke test: bring up dev telemetry stack and verify demo emitter probe."""
    up_cmd = ["docker", "compose", "-f", DEV_COMPOSE, "up", "-d"]
    down_cmd = ["docker", "compose", "-f", DEV_COMPOSE, "down"]

    subprocess.run(up_cmd, check=True)

    try:
        # Poll the demo emitter HTTP probe
        start = time.time()
        success = False
        while time.time() - start < 60:
            try:
                r = requests.get("http://localhost:8080/", timeout=3)
                if r.status_code == 200:
                    success = True
                    break
            except requests.RequestException:
                pass
            time.sleep(1)

        assert success, "demo emitter probe did not respond in time"

    finally:
        subprocess.run(down_cmd, check=False)

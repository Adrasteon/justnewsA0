#!/usr/bin/env python3
import os
import subprocess
import time

def check_agent_status(agent_name, port):
    """Check if the agent is running on the specified port."""
    try:
        result = subprocess.run(['ss', '-tuln'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        if f":{port}" in output:
            print(f"{agent_name} is running on port {port}")
            return True
        else:
            print(f"{agent_name} is not running on port {port}")
            return False
    except Exception as e:
        print(f"Error checking status for {agent_name}: {e}")
        return False

def check_service_status(service_name):
    """Check if the service is active using systemctl."""
    try:
        result = subprocess.run(['systemctl', 'is-active', service_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        status = result.stdout.decode('utf-8').strip()
        if status == 'active':
            print(f"{service_name} is active")
            return True
        else:
            print(f"{service_name} is not active")
            return False
    except Exception as e:
        print(f"Error checking status for {service_name}: {e}")
        return False

def check_all_agents():
    """Check if all agents are running."""
    agents = {
        "MCP Bus": 8000,
        "Scout Agent": 8002,
        "Fact Checker Agent": 8003,
        "Analyst Agent": 8004,
        "Synthesizer Agent": 8005,
        "Critic Agent": 8006,
        "Reasoning Agent": 8008,
        "Crawler Agent": 8015,
        "Crawler Control": 8016
    }
    all_running = True
    for agent, port in agents.items():
        if not check_agent_status(agent, port):
            all_running = False
    return all_running

def check_all_services():
    """Check if all services are running."""
    services = ["nginx", "postgresql", "redis"]  # Replace with actual services
    all_running = True
    for service in services:
        if not check_service_status(service):
            all_running = False
    return all_running

def check_mps_nvml_status():
    """Check MPS and NVML status."""
    print("Checking MPS and NVML status...")

    # Check MPS status
    try:
        result = subprocess.run(['nvidia-cuda-mps-control', '-c', 'get_server_list'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("MPS: Running")
        else:
            print("MPS: Not running")
    except Exception as e:
        print(f"Error checking MPS status: {e}")

    # Check NVML status
    try:
        result = subprocess.run(['python3', '-c', 'import pynvml; pynvml.nvmlInit(); print("NVML: Initialized successfully")'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("NVML: Initialized successfully")
        else:
            print("NVML: Initialization failed")
    except Exception as e:
        print(f"Error checking NVML status: {e}")

def main():
    """Main function to check system status."""
    print("Checking agent and service status...")
    agents_ok = check_all_agents()
    services_ok = check_all_services()

    # Test for MPS and NVML status
    check_mps_nvml_status()

    # Summary
    print("\nSystem Status Summary:")
    if agents_ok and services_ok:
        print("All agents and services are running.")
    else:
        if not agents_ok:
            print("Some agents are not running.")
        if not services_ok:
            print("Some services are not running.")

if __name__ == "__main__":
    main()
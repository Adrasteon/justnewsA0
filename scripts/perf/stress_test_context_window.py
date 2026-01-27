#!/usr/bin/env python3
"""
Stress Test Context Window Limits for vLLM

This script iteratively sends inference requests with increasing input token lengths
to a local vLLM server to determine the maximum safe context window before OOM or degradation.
"""

import argparse
import os
import random
import string
import time

import requests


def generate_prompt(approx_tokens: int) -> str:
    # Approx 4 chars per token for random text
    # This is a rough heuristic. For more precision, we'd use a tokenizer,
    # but for stress testing memory, this is usually sufficient.
    num_chars = approx_tokens * 4
    return ''.join(random.choices(string.ascii_letters + " ", k=num_chars))

def run_stress_test(base_url: str, start_tokens: int, max_tokens: int, step_tokens: int):
    print(f"Starting context stress test against {base_url}")
    print(f"Range: {start_tokens} -> {max_tokens} tokens (step: {step_tokens})")

    current_tokens = start_tokens

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ.get('VLLM_API_KEY', 'dummy')}"
    }

    while current_tokens <= max_tokens:
        print(f"\n--- Testing context size: ~{current_tokens} tokens ---")
        prompt = generate_prompt(current_tokens)

        payload = {
            "model": "mistralai/Mistral-7B-Instruct-v0.3",
            "prompt": prompt,
            "max_tokens": 10, # We only care about processing the input
            "temperature": 0.0
        }

        start_time = time.time()
        try:
            response = requests.post(f"{base_url}/v1/completions", json=payload, headers=headers, timeout=120)
            duration = time.time() - start_time

            if response.status_code == 200:
                print(f"✅ Success! Latency: {duration:.2f}s")
                # Optional: Check usage info if available to verify token count
                try:
                    usage = response.json().get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", "unknown")
                    print(f"   Actual Prompt Tokens: {prompt_tokens}")
                except:
                    pass
            else:
                print(f"❌ Failed! Status Code: {response.status_code}")
                print(f"   Error: {response.text}")
                break

        except requests.exceptions.RequestException as e:
            print(f"❌ Connection/Timeout Error: {e}")
            break

        current_tokens += step_tokens
        time.sleep(1) # Brief pause to allow things to settle

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="vLLM Context Stress Tester")
    parser.add_argument("--url", default="http://127.0.0.1:7060", help="vLLM base URL")
    parser.add_argument("--start", type=int, default=1000, help="Start token count")
    parser.add_argument("--max", type=int, default=16000, help="Max token count")
    parser.add_argument("--step", type=int, default=1000, help="Step size")

    args = parser.parse_args()

    # Ensure URL doesn't have trailing /v1 if we add it, or handle it smartly
    # The snippet uses /v1/completions, so base url should be host:port
    base_url = args.url.rstrip("/")

    try:
        run_stress_test(base_url, args.start, args.max, args.step)
    except KeyboardInterrupt:
        print("\nTest cancelled by user.")

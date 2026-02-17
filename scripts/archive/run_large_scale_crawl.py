#!/usr/bin/env python3
"""
Quick Start Guide: Large-Scale Multi-Site Crawl with AI Quality Assessment

This script demonstrates how to execute a large run against multiple sites
asynchronously using AI for quality testing in the JustNews V4 system.

Prerequisites:
1. All agents must be running (use ./start_services_daemon.sh)
2. MariaDB database must be available (PostgreSQL support is deprecated)
3. Model cache directories must exist

Usage Examples:
    # Basic usage - crawl 5 sites with default settings
    python run_large_scale_crawl.py

    # Test mode - small scale test
    python run_large_scale_crawl.py --test

    # Custom configuration
    python run_large_scale_crawl.py --sites bbc cnn --articles 25 --concurrent 3

    # AI-enhanced mode only
    python run_large_scale_crawl.py --mode ai_enhanced --quality 0.7
"""

import subprocess
import sys
from pathlib import Path


def check_services_running():
    """Check if required services are running"""
    print("🔍 Checking if JustNews services are running...")

    required_ports = {
        8000: "MCP Bus",
        8002: "Scout Agent",
        8009: "NewsReader Agent",
        8007: "Memory Agent",
    }

    missing_services = []
    for port, service in required_ports.items():
        try:
            result = subprocess.run(
                ["ss", "-ltn", f"sport = :{port}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "LISTEN" not in result.stdout:
                missing_services.append(f"{service} (port {port})")
        except Exception:
            missing_services.append(f"{service} (port {port})")

    if missing_services:
        print("❌ Missing services:")
        for service in missing_services:
            print(f"   - {service}")
        print("\n💡 Start services with: ./start_services_daemon.sh")
        return False

    print("✅ All required services are running")
    return True


def run_large_scale_crawl(args=None):
    """Execute the large-scale crawl"""
    if args is None:
        args = []

    print("🚀 Starting Large-Scale Multi-Site Crawl...")
    print("=" * 60)

    # Build command
    cmd = [sys.executable, "large_scale_multi_site_crawl.py"] + args

    print(f"📋 Command: {' '.join(cmd)}")
    print()

    try:
        # Run the crawl
        result = subprocess.run(cmd, cwd=Path(__file__).parent)

        if result.returncode == 0:
            print("\n🎉 Large-scale crawl completed successfully!")
            print("📄 Check ./large_scale_crawl_results/ for detailed reports")
        else:
            print(f"\n❌ Crawl failed with exit code: {result.returncode}")

        return result.returncode

    except KeyboardInterrupt:
        print("\n⏹️ Crawl interrupted by user")
        return 130
    except Exception as e:
        print(f"\n❌ Error running crawl: {e}")
        return 1


def main():
    """Main execution with argument parsing"""
    import argparse

    parser = argparse.ArgumentParser(description="Run Large-Scale Multi-Site Crawl")
    parser.add_argument(
        "--test", action="store_true", help="Run in test mode with small numbers"
    )
    parser.add_argument(
        "--sites",
        nargs="+",
        help="Specific sites to crawl (default: bbc cnn reuters nytimes guardian)",
    )
    parser.add_argument("--articles", type=int, help="Articles per site (default: 50)")
    parser.add_argument("--concurrent", type=int, help="Concurrent sites (default: 5)")
    parser.add_argument(
        "--mode",
        choices=["ultra_fast", "ai_enhanced", "mixed"],
        help="Crawl mode (default: mixed)",
    )
    parser.add_argument(
        "--quality", type=float, help="Quality threshold (default: 0.6)"
    )

    args = parser.parse_args()

    # Check services first
    if not check_services_running():
        sys.exit(1)

    # Build arguments for the crawl script
    crawl_args = []

    if args.test:
        crawl_args.extend(["--test-mode"])
        print("🧪 Running in TEST MODE")
    else:
        if args.sites:
            crawl_args.extend(["--sites"] + args.sites)
        if args.articles:
            crawl_args.extend(["--articles-per-site", str(args.articles)])
        if args.concurrent:
            crawl_args.extend(["--concurrent-sites", str(args.concurrent)])
        if args.mode:
            crawl_args.extend(["--mode", args.mode])
        if args.quality:
            crawl_args.extend(["--quality-threshold", str(args.quality)])

    # Show configuration
    print("\n⚙️ Crawl Configuration:")
    if args.test:
        print("   Mode: Test (small scale)")
        print("   Sites: bbc, cnn (first 2)")
        print("   Articles per site: 5")
        print("   Concurrent sites: 2")
    else:
        print(f"   Sites: {args.sites or 'bbc, cnn, reuters, nytimes, guardian'}")
        print(f"   Articles per site: {args.articles or 50}")
        print(f"   Concurrent sites: {args.concurrent or 5}")
        print(f"   Mode: {args.mode or 'mixed'}")
        print(f"   Quality threshold: {args.quality or 0.6}")

    print("\n🤖 AI Quality Assessment:")
    print("   • LLaMA-3-8B for content classification")
    print("   • BERT models for news detection and quality")
    print("   • RoBERTa for sentiment analysis")
    print("   • Bias detection models")
    print("   • LLaVA for visual content analysis")
    print("   • NewsReader screenshot analysis")

    # Confirm before starting
    if not args.test:
        try:
            response = input("\n🚀 Start large-scale crawl? (y/N): ").strip().lower()
            if response not in ["y", "yes"]:
                print("❌ Crawl cancelled")
                sys.exit(0)
        except KeyboardInterrupt:
            print("\n❌ Crawl cancelled")
            sys.exit(0)

    # Run the crawl
    exit_code = run_large_scale_crawl(crawl_args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

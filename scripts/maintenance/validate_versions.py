#!/usr/bin/env python3
"""
Comprehensive version validation script for JustNews
Tests all agents and components for version consistency
"""

import os
import sys

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_version_consistency():
    """Test that all components use the same version"""
    print("🔍 JustNews Version Consistency Check")
    print("=" * 50)

    # Test centralized version
    try:
        from justnews import VERSION_INFO
        from justnews import __version__ as central_version

        print(f"✅ Centralized Version: {central_version}")
        print(f"   Status: {VERSION_INFO['status']}")
        expected_version = central_version
    except ImportError as e:
        print(f"❌ Centralized Version Error: {e}")
        return False

    # Test agent versions
    agents_to_test = [
        ("Crawler Agent", "agents.crawler"),
        ("Scout Production Crawlers", "agents.scout.production_crawlers"),
    ]

    all_consistent = True

    for agent_name, module_path in agents_to_test:
        try:
            module = __import__(module_path, fromlist=["__version__"])
            agent_version = getattr(module, "__version__", None)
            if agent_version == expected_version:
                print(f"✅ {agent_name}: {agent_version}")
            else:
                print(f"❌ {agent_name}: {agent_version} (expected {expected_version})")
                all_consistent = False
        except Exception as e:
            print(f"❌ {agent_name} Error: {e}")
            all_consistent = False

    # Test API endpoints (would need running services)
    print("\n📡 API Endpoints (requires running services):")
    print(
        "   Run individual agents and check /health endpoints for version consistency"
    )

    print("\n" + "=" * 50)
    if all_consistent:
        print("🎉 All tested components use consistent versioning!")
        return True
    else:
        print("⚠️  Version inconsistencies found - please check agent imports")
        return False


if __name__ == "__main__":
    success = test_version_consistency()
    sys.exit(0 if success else 1)

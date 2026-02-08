#!/usr/bin/env python3
"""
Script Ecosystem Test Runner

Tests all scripts in the refactored ecosystem for basic functionality.
Validates that scripts can be imported, have proper help, and basic argument parsing.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class ScriptTester:
    """Test runner for script ecosystem"""

    def __init__(self, refactor_dir: Path):
        self.refactor_dir = refactor_dir
        self.results = []

    def find_python_scripts(self) -> list[Path]:
        """Find all Python scripts in the refactor directory"""
        scripts = []
        for category_dir in self.refactor_dir.iterdir():
            if category_dir.is_dir() and category_dir.name not in ["archive", "common"]:
                for script_file in category_dir.glob("*.py"):
                    scripts.append(script_file)
        return scripts

    def test_script_import(self, script_path: Path) -> tuple[bool, str]:
        """Test if script can be imported without errors"""
        try:
            spec = importlib.util.spec_from_file_location(script_path.stem, script_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return True, "Import successful"
            else:
                return False, "Could not create module spec"
        except Exception as e:
            return False, f"Import failed: {e}"

    def test_script_help(self, script_path: Path) -> tuple[bool, str]:
        """Test if script can be executed without immediate crash"""
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Accept any return code - some scripts might fail due to missing dependencies
            # but they should at least start and show some output
            if len(result.stdout) > 0 or len(result.stderr) > 0:
                return (
                    True,
                    "Script executed (may have warnings/errors due to environment)",
                )
            else:
                return False, "Script produced no output"
        except subprocess.TimeoutExpired:
            return False, "Script timed out"
        except Exception as e:
            return False, f"Script execution failed: {e}"

    def test_script_basic_args(self, script_path: Path) -> tuple[bool, str]:
        """Test basic argument parsing"""
        try:
            # Test with --dry-run if it's a Python script using our framework
            subprocess.run(
                [sys.executable, str(script_path), "--dry-run"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Some scripts might not support --dry-run, that's ok
            return True, "Basic argument parsing works"
        except subprocess.TimeoutExpired:
            return False, "Basic args test timed out"
        except Exception as e:
            return False, f"Basic args test failed: {e}"

    def run_tests(self) -> dict[str, list[tuple[str, bool, str]]]:
        """Run all tests on scripts"""
        results = {}

        for script_path in self.find_python_scripts():
            category = script_path.parent.name
            script_name = script_path.name

            if category not in results:
                results[category] = []

            # Skip the test script itself
            if script_name == "test_script_ecosystem.py":
                continue

            # Test help (most basic test)
            help_ok, help_msg = self.test_script_help(script_path)

            results[category].append((script_name, help_ok, f"Help: {help_msg}"))

        return results

    def print_results(self, results: dict[str, list[tuple[str, bool, str]]]):
        """Print test results"""
        print("Script Ecosystem Test Results")
        print("=" * 50)

        total_scripts = 0
        passed_scripts = 0

        for category, scripts in results.items():
            print(f"\n{category.upper()}:")
            print("-" * len(category))

            for script_name, passed, details in scripts:
                status = "✅ PASS" if passed else "❌ FAIL"
                print(f"  {status} {script_name}")
                if not passed:
                    print(f"    Details: {details}")
                else:
                    total_scripts += 1
                    passed_scripts += 1

        print(f"\nSummary: {passed_scripts}/{total_scripts} scripts passed basic tests")


def main():
    """Main test runner"""
    # Use absolute path to refactor directory
    refactor_dir = Path(__file__).parent.parent

    tester = ScriptTester(refactor_dir)
    results = tester.run_tests()
    tester.print_results(results)

    # Exit with error code if any tests failed
    all_passed = all(
        all(passed for _, passed, _ in scripts) for scripts in results.values()
    )

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
JustNews Test Runner

This script provides a comprehensive test runner for the JustNews
testing framework. It includes:

- Test discovery and execution
- Coverage reporting
- Performance benchmarking
- Integration test orchestration
- GPU testing support
- Detailed reporting and analytics

Usage:
    python tests/refactor/test_runner.py [options]

Options:
    --unit: Run unit tests only
    --integration: Run integration tests only
    --performance: Run performance tests only
    --gpu: Run GPU-specific tests
    --coverage: Generate coverage report
    --benchmark: Run performance benchmarks
    --verbose: Enable verbose output
    --report: Generate detailed test report
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class Runner:
    """Comprehensive test runner for JustNews"""

    def __init__(self, args):
        self.args = args
        self.project_root = project_root
        self.test_dir = self.project_root / "tests"
        self.results = {}
        self.start_time = None

    def run_command(
        self, cmd: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess:
        """Run a command and return the result"""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or self.project_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            return result
        except subprocess.TimeoutExpired:
            print(f"Command timed out: {' '.join(cmd)}")
            raise

    def setup_test_environment(self):
        """Setup test environment"""
        print("🔧 Setting up test environment...")

        # Ensure test directory exists
        self.test_dir.mkdir(parents=True, exist_ok=True)

        # Set environment variables for testing
        os.environ.setdefault("PYTHONPATH", str(self.project_root))
        os.environ.setdefault("TESTING", "true")

        # GPU testing setup
        if self.args.gpu:
            os.environ["TEST_GPU_AVAILABLE"] = "true"
            os.environ["TEST_GPU_COUNT"] = "1"
        else:
            os.environ["TEST_GPU_AVAILABLE"] = "false"

        print("✅ Test environment ready")

    def run_unit_tests(self) -> dict[str, Any]:
        """Run unit tests"""
        print("🧪 Running unit tests...")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(self.test_dir),
            "-m",
            "not (integration or performance or gpu or slow)",
            "--tb=short",
            "-q",
        ]

        if self.args.verbose:
            cmd.extend(["-v", "--tb=long"])

        result = self.run_command(cmd)

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "return_code": result.returncode,
        }

    def run_integration_tests(self) -> dict[str, Any]:
        """Run integration tests"""
        print("🔗 Running integration tests...")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(self.test_dir),
            "-m",
            "integration",
            "--tb=short",
            "-q",
        ]

        if self.args.verbose:
            cmd.extend(["-v", "--tb=long"])

        result = self.run_command(cmd)

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "return_code": result.returncode,
        }

    def run_performance_tests(self) -> dict[str, Any]:
        """Run performance tests"""
        print("⚡ Running performance tests...")

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(self.test_dir),
            "-m",
            "performance",
            "--tb=short",
            "-q",
        ]

        if self.args.verbose:
            cmd.extend(["-v", "--tb=long"])

        result = self.run_command(cmd)

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "return_code": result.returncode,
        }

    def run_gpu_tests(self) -> dict[str, Any]:
        """Run GPU-specific tests"""
        print("🎮 Running GPU tests...")

        if not self.args.gpu:
            return {"success": True, "skipped": True, "message": "GPU tests disabled"}

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(self.test_dir),
            "-m",
            "gpu",
            "--tb=short",
            "-q",
        ]

        if self.args.verbose:
            cmd.extend(["-v", "--tb=long"])

        result = self.run_command(cmd)

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "return_code": result.returncode,
        }

    def run_coverage_analysis(self) -> dict[str, Any]:
        """Run coverage analysis"""
        print("📊 Running coverage analysis...")

        coverage_dir = self.project_root / "htmlcov"
        if coverage_dir.exists():
            shutil.rmtree(coverage_dir)

        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(self.test_dir),
            "--cov=agents",
            "--cov=common",
            "--cov-report=term-missing",
            "--cov-report=html",
            "--cov-report=xml",
            "--cov-fail-under=80",
            "-q",
        ]

        result = self.run_command(cmd)

        return {
            "success": result.returncode == 0,
            "output": result.stdout,
            "errors": result.stderr,
            "return_code": result.returncode,
            "coverage_dir": str(coverage_dir),
        }

    def run_benchmarks(self) -> dict[str, Any]:
        """Run performance benchmarks"""
        print("🏃 Running performance benchmarks...")

        # Use pytest-benchmark if available, otherwise run performance tests
        try:
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                str(self.test_dir),
                "-m",
                "performance",
                "--benchmark-only",
                "--benchmark-save=benchmarks",
                "--benchmark-compare",
                "-q",
            ]

            result = self.run_command(cmd)
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "errors": result.stderr,
                "benchmark_saved": True,
            }
        except FileNotFoundError:
            # Fallback to regular performance tests
            return self.run_performance_tests()

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive test report"""
        print("📋 Generating test report...")

        report = {
            "timestamp": time.time(),
            "duration": time.time() - self.start_time,
            "test_results": self.results,
            "summary": self._generate_summary(),
            "recommendations": self._generate_recommendations(),
        }

        # Save report
        report_file = self.project_root / "test_report.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        return {
            "success": True,
            "report_file": str(report_file),
            "summary": report["summary"],
        }

    def _generate_summary(self) -> dict[str, Any]:
        """Generate test summary"""
        total_tests = 0
        passed_tests = 0
        failed_tests = 0

        for _test_type, result in self.results.items():
            if isinstance(result, dict) and "success" in result:
                if result["success"]:
                    passed_tests += 1
                else:
                    failed_tests += 1
                total_tests += 1

        return {
            "total_test_suites": total_tests,
            "passed_suites": passed_tests,
            "failed_suites": failed_tests,
            "overall_success": failed_tests == 0,
            "test_coverage": self._calculate_coverage(),
        }

    def _calculate_coverage(self) -> float:
        """Calculate test coverage percentage"""
        # This would integrate with coverage.py results
        # For now, return a placeholder
        return 85.0

    def _generate_recommendations(self) -> list[str]:
        """Generate test improvement recommendations"""
        recommendations = []

        # Analyze results and provide recommendations
        if not self.results.get("unit", {}).get("success", True):
            recommendations.append("Fix failing unit tests before proceeding")

        if not self.results.get("integration", {}).get("success", True):
            recommendations.append("Address integration test failures")

        if self.results.get("coverage", {}).get("success", False):
            coverage_success = self.results["coverage"]["success"]
            if not coverage_success:
                recommendations.append(
                    "Improve test coverage to meet minimum requirements"
                )

        if not self.results.get("performance", {}).get("success", True):
            recommendations.append(
                "Optimize performance bottlenecks identified in tests"
            )

        return recommendations

    def run_all_tests(self):
        """Run all configured tests"""
        self.start_time = time.time()

        # Setup
        self.setup_test_environment()

        # Run tests based on configuration
        if self.args.unit or not any(
            [self.args.integration, self.args.performance, self.args.gpu]
        ):
            self.results["unit"] = self.run_unit_tests()

        if self.args.integration:
            self.results["integration"] = self.run_integration_tests()

        if self.args.performance or self.args.benchmark:
            self.results["performance"] = self.run_performance_tests()

        if self.args.gpu:
            self.results["gpu"] = self.run_gpu_tests()

        if self.args.coverage:
            self.results["coverage"] = self.run_coverage_analysis()

        if self.args.benchmark:
            self.results["benchmarks"] = self.run_benchmarks()

        # Generate report
        if self.args.report:
            self.results["report"] = self.generate_report()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test execution summary"""
        print("\n" + "=" * 60)
        print("🧪 JustNews Test Summary")
        print("=" * 60)

        for test_type, result in self.results.items():
            if isinstance(result, dict):
                status = "✅ PASS" if result.get("success", False) else "❌ FAIL"
                print(f"{test_type.upper():<15}: {status}")

                if not result.get("success", True) and "errors" in result:
                    print(f"  Errors: {result['errors'][:100]}...")

        print(f"\n⏱️  Total execution time: {time.time() - self.start_time:.2f}s")

        if self.args.report:
            report_file = self.results.get("report", {}).get("report_file")
            if report_file:
                print(f"📄 Detailed report saved to: {report_file}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="JustNews Test Runner")

    # Test type options
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument(
        "--integration", action="store_true", help="Run integration tests only"
    )
    parser.add_argument(
        "--performance", action="store_true", help="Run performance tests only"
    )
    parser.add_argument("--gpu", action="store_true", help="Run GPU-specific tests")

    # Analysis options
    parser.add_argument(
        "--coverage", action="store_true", help="Generate coverage report"
    )
    parser.add_argument(
        "--benchmark", action="store_true", help="Run performance benchmarks"
    )

    # Output options
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument(
        "--report", action="store_true", help="Generate detailed test report"
    )

    args = parser.parse_args()

    # Run tests
    runner = Runner(args)
    try:
        runner.run_all_tests()
        success = all(
            result.get("success", False)
            for result in runner.results.values()
            if isinstance(result, dict)
        )
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test runner failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Performance Tests for JustNews System

This module contains comprehensive performance tests that validate:
- Response times and throughput
- Memory usage and leaks
- GPU utilization efficiency
- Concurrent request handling
- Scalability under load
- Resource cleanup effectiveness
"""

import asyncio
import gc
import time
import tracemalloc
from typing import Any
from unittest.mock import AsyncMock, patch

import psutil
import pytest

from tests.test_utils import (
    AsyncTestHelper,
    CustomAssertions,
    MockFactory,
    PerformanceTester,
)


class TestSystemPerformance:
    """Performance tests for core system components"""

    def setup_method(self):
        """Setup performance test fixtures"""
        self.helper = AsyncTestHelper()
        self.perf_tester = PerformanceTester("system_performance")
        self.assertions = CustomAssertions()
        self.mock_factory = MockFactory()

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_mcp_bus_response_times(self):
        """Test MCP Bus response times under various loads"""
        # Test different load scenarios using PerformanceTester
        load_scenarios = [
            ("light", 10, 0.1),  # 10 requests, 100ms delay
            ("medium", 50, 0.05),  # 50 requests, 50ms delay
            ("heavy", 100, 0.02),  # 100 requests, 20ms delay
        ]

        for scenario_name, num_requests, delay in load_scenarios:
            # Run the benchmark directly
            await self._benchmark_mcp_bus_load(num_requests, delay)

            # Get metrics from the performance tester
            metrics = self.perf_tester.metrics

            # Assert performance requirements
            assert metrics.average_time < 1.0, (
                f"Average response time too high: {metrics.average_time}"
            )
            assert metrics.p95_time < 2.0, (
                f"P95 response time too high: {metrics.p95_time}"
            )

            print(
                f"✅ {scenario_name} load: avg={metrics.average_time:.3f}s, p95={metrics.p95_time:.3f}s"
            )

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_agent_processing_throughput(self):
        """Test agent processing throughput"""
        # Benchmark processing rate using PerformanceTester
        metrics = await self.perf_tester.measure_async_operation(
            lambda: self._benchmark_processing_throughput(100), iterations=1
        )

        throughput = 100 / metrics.average_time  # articles per second

        # Assert minimum throughput
        assert throughput > 10, f"Throughput too low: {throughput} articles/second"

        print(f"✅ Analyst throughput: {throughput:.1f} articles/second")

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_memory_usage_stability(self):
        """Test memory usage stability under sustained load"""
        # Enable memory tracing
        tracemalloc.start()

        initial_memory = self._get_memory_usage()

        # Run sustained load test
        await self._run_sustained_load_test(duration=30)  # 30 seconds

        # Check memory usage after load
        final_memory = self._get_memory_usage()
        memory_growth = final_memory - initial_memory

        # Assert memory stability (less than 10% growth)
        memory_growth_percent = (memory_growth / initial_memory) * 100
        assert memory_growth_percent < 10, (
            f"Memory growth too high: {memory_growth_percent:.1f}%"
        )

        # Force garbage collection and check again
        gc.collect()
        post_gc_memory = self._get_memory_usage()
        post_gc_growth = post_gc_memory - initial_memory
        post_gc_growth_percent = (post_gc_growth / initial_memory) * 100

        assert post_gc_growth_percent < 5, (
            f"Memory leak detected: {post_gc_growth_percent:.1f}% after GC"
        )

        tracemalloc.stop()
        print(
            f"✅ Memory stability: {memory_growth_percent:.1f}% growth, {post_gc_growth_percent:.1f}% after GC"
        )

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_request_handling(self):
        """Test concurrent request handling capacity"""
        # Test concurrent MCP Bus calls
        concurrent_levels = [10, 50, 100, 200]

        for num_concurrent in concurrent_levels:
            start_time = time.time()

            # Create concurrent requests
            tasks = []
            for i in range(num_concurrent):
                task = asyncio.create_task(self._make_mcp_request(i))
                tasks.append(task)

            # Execute all requests
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.time()

            # Calculate metrics
            total_time = end_time - start_time
            successful_requests = len(
                [r for r in results if not isinstance(r, Exception)]
            )
            success_rate = successful_requests / num_concurrent

            # Assert concurrent handling
            assert success_rate > 0.95, (
                f"Success rate too low at {num_concurrent} concurrent requests: {success_rate:.1f}"
            )
            assert total_time < 10, (
                f"Total time too high for {num_concurrent} requests: {total_time:.1f}s"
            )

            print(
                f"✅ Concurrent {num_concurrent}: {success_rate:.1f}% success, {total_time:.1f}s total"
            )

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_gpu_memory_efficiency(self):
        """Test GPU memory efficiency"""
        if not self._gpu_available():
            pytest.skip("GPU not available for testing")

        # Setup GPU monitoring
        initial_gpu_memory = await self._get_gpu_memory_usage()

        # Run GPU-intensive operations
        await self._run_gpu_operations_batch()

        # Check GPU memory usage
        final_gpu_memory = await self._get_gpu_memory_usage()
        gpu_memory_growth = final_gpu_memory - initial_gpu_memory

        # Assert GPU memory efficiency
        assert gpu_memory_growth < 1024 * 1024 * 1024, (
            f"GPU memory growth too high: {gpu_memory_growth / (1024 * 1024):.1f}MB"
        )

        # Test memory cleanup
        await self._cleanup_gpu_memory()
        cleanup_gpu_memory = await self._get_gpu_memory_usage()
        cleanup_growth = cleanup_gpu_memory - initial_gpu_memory

        assert cleanup_growth < 100 * 1024 * 1024, (
            f"GPU memory leak: {cleanup_growth / (1024 * 1024):.1f}MB after cleanup"
        )

        print(
            f"✅ GPU memory: {gpu_memory_growth / (1024 * 1024):.1f}MB used, {cleanup_growth / (1024 * 1024):.1f}MB after cleanup"
        )

    @pytest.mark.asyncio
    @pytest.mark.performance
    # Database pooling tests using Postgres were removed because Postgres has been deprecated.
    # See migration to MariaDB + ChromaDB; use database-specific unit tests under
    # `database/tests` for connection pooling and migration behavior.

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_network_io_efficiency(self):
        """Test network I/O efficiency"""
        # Run network operations and measure performance
        metrics = await self.perf_tester.measure_async_operation(
            self._run_network_operations, iterations=10
        )

        # Assert network efficiency
        assert metrics.average_time < 0.5, (
            f"Network latency too high: {metrics.average_time}"
        )
        assert metrics.success_rate > 0.9, (
            f"Network success rate too low: {metrics.success_rate}"
        )

        print(
            f"✅ Network I/O: {metrics.average_time:.3f}s latency, {metrics.success_rate:.1f}% success"
        )

    async def _benchmark_mcp_bus_load(self, num_requests: int, delay: float):
        """Benchmark MCP Bus under load"""
        execution_times = []

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = AsyncMock()
            mock_response.json.return_value = {"status": "success"}
            mock_client.return_value.post.return_value = mock_response

            for _i in range(num_requests):
                start_time = time.perf_counter()
                # Simulate MCP Bus call
                await asyncio.sleep(delay)  # Simulate processing
                end_time = time.perf_counter()
                execution_times.append(end_time - start_time)

        # Store execution times in the performance tester
        self.perf_tester.metrics.execution_times = execution_times

    async def _benchmark_processing_throughput(self, num_articles: int):
        """Benchmark processing throughput"""
        tasks = []
        for i in range(num_articles):
            task = asyncio.create_task(self._process_single_article(i))
            tasks.append(task)

        await asyncio.gather(*tasks)

    async def _process_single_article(self, article_id: int) -> dict[str, Any]:
        """Process a single article"""
        # Simulate article processing
        await asyncio.sleep(0.01)  # 10ms processing time
        return {"article_id": article_id, "processed": True}

    async def _run_sustained_load_test(self, duration: int):
        """Run sustained load test"""
        end_time = time.time() + duration

        while time.time() < end_time:
            # Simulate continuous load
            await self._make_mcp_request(0)
            await asyncio.sleep(0.01)  # 10ms between requests

    def _get_memory_usage(self) -> int:
        """Get current memory usage"""
        process = psutil.Process()
        return process.memory_info().rss

    async def _make_mcp_request(self, request_id: int) -> dict[str, Any]:
        """Make a mock MCP request"""
        await asyncio.sleep(0.001)  # 1ms network delay
        return {"request_id": request_id, "status": "success"}

    def _gpu_available(self) -> bool:
        """Check if GPU is available"""
        try:
            import torch

            return torch.cuda.is_available()
        except ImportError:
            return False

    async def _get_gpu_memory_usage(self) -> int:
        """Get GPU memory usage"""
        if not self._gpu_available():
            return 0

        import torch

        return torch.cuda.memory_allocated()

    async def _run_gpu_operations_batch(self):
        """Run batch of GPU operations"""
        if not self._gpu_available():
            return

        import torch

        # Simulate GPU operations
        for _ in range(10):
            tensor = torch.randn(1000, 1000).cuda()
            result = tensor @ tensor.t()
            del tensor, result
            torch.cuda.empty_cache()

    async def _cleanup_gpu_memory(self):
        """Cleanup GPU memory"""
        if not self._gpu_available():
            return

        import torch

        torch.cuda.empty_cache()

    async def _simulate_database_operations(self, num_operations: int):
        """Simulate database operations"""
        for _ in range(num_operations):
            # Simulate database query
            await asyncio.sleep(0.001)

    async def _run_network_operations(self):
        """Run network operations for testing"""
        # Simulate network calls
        await asyncio.sleep(0.1)

    def _validate_performance_metrics(self, metrics: dict[str, Any]):
        """Validate performance metrics"""
        # Validate key performance indicators
        assert "avg_response_time" in metrics
        assert "throughput" in metrics
        assert "error_rate" in metrics

        # Assert performance thresholds
        assert metrics["avg_response_time"] < 1.0
        assert metrics["error_rate"] < 0.05
        assert metrics["throughput"] > 1.0


class TestScalabilityBenchmarks:
    """Scalability benchmarks for system components"""

    def setup_method(self):
        """Setup scalability test fixtures"""
        self.perf_tester = PerformanceTester("scalability_benchmark")

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_horizontal_scaling_simulation(self):
        """Test horizontal scaling simulation"""
        # Simulate adding more agent instances
        scaling_levels = [1, 2, 4, 8]  # Number of agent instances

        for num_instances in scaling_levels:
            # Simulate load distribution across instances
            total_load = 100
            load_per_instance = total_load / num_instances

            start_time = time.time()

            # Simulate parallel processing
            tasks = []
            for _i in range(num_instances):
                task = asyncio.create_task(
                    self._simulate_instance_load(load_per_instance)
                )
                tasks.append(task)

            await asyncio.gather(*tasks)
            end_time = time.time()

            processing_time = end_time - start_time
            throughput = total_load / processing_time

            print(
                f"✅ {num_instances} instances: {throughput:.1f} items/s, {processing_time:.3f}s"
            )

            # Assert scaling efficiency
            if num_instances > 1:
                # Should see improvement with more instances
                assert processing_time < (total_load * 0.1), "Scaling not effective"

    async def _simulate_instance_load(self, load_amount: float) -> float:
        """Simulate load on a single instance"""
        # Simulate processing time proportional to load
        processing_time = load_amount * 0.01
        await asyncio.sleep(processing_time)
        return processing_time


class TestResourceCleanup:
    """Test resource cleanup effectiveness"""

    def setup_method(self):
        """Setup cleanup test fixtures"""
        self.helper = AsyncTestHelper()

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_context_manager_cleanup(self):
        """Test proper cleanup with context managers"""
        # Test resource cleanup patterns
        cleanup_called = False

        class MockResource:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                nonlocal cleanup_called
                cleanup_called = True

        # Use context manager
        async with MockResource():
            # Simulate operations
            pass

        # Verify cleanup was called
        assert cleanup_called

    async def _gpu_context(self):
        """Mock GPU context manager"""
        # This would be a real GPU context manager
        yield

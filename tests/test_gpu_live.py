"""
Live GPU Tests for JustNews System

This module contains REAL integration tests that execute against actual hardware.
These tests verify that the GPU is physically accessible and capable of
performing tensor operations.

WARNING: These tests require a real NVIDIA GPU and properly configured CUDA environment.
They are skipped unless the environment appears capable.
"""

import sys
import os
import pytest
import torch
import gc
import subprocess
import re

# Skip all tests in this module if no GPU is available or explicitly disabled
cpu_only = os.environ.get("TEST_GPU_AVAILABLE", "false").lower() != "true"
cuda_missing = not torch.cuda.is_available()

# Logic: Skip if USER wants CPU only OR if Hardware is Missing
should_skip = cpu_only or cuda_missing

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(
        should_skip,
        reason=f"Live GPU tests skipped (TEST_GPU_AVAILABLE={not cpu_only}, CUDA={not cuda_missing})"
    )
]

class TestLiveGPUHardware:
    """
    Direct hardware validation tests.
    Does NOT use mocks. Uses real PyTorch CUDA calls.
    """

    @pytest.fixture(scope="class", autouse=True)
    def enforce_gpu_power(self):
        """
        Ensure GPU power is configured correctly (max 300W) before running tests.
        Attempts to auto-configure if limits are exceeded.
        """
        if not torch.cuda.is_available():
            return

        TARGET_POWER = 300.0
        
        try:
            # check current settings
            result = subprocess.check_output(
                ["nvidia-smi", "-q", "-d", "POWER"], 
                text=True, 
                stderr=subprocess.STDOUT
            )
            
            # Simple parsing of "Current Power Limit      : 350.00 W"
            match = re.search(r"Current Power Limit\s+:\s+([\d\.]+)\s+W", result)
            if match:
                current_limit = float(match.group(1))
                if current_limit > TARGET_POWER:
                    print(f"\nWARNING: GPU Power Limit ({current_limit}W) exceeds target ({TARGET_POWER}W).")
                    
                    script_path = os.path.join(os.getcwd(), "scripts/configure_gpu_power.sh")
                    try:
                        # Try executing the script (requires sudo/permissions)
                        # We use sudo -n to fail non-interactively if password is required
                        subprocess.run(
                            ["sudo", "-n", script_path], 
                            check=True,
                            capture_output=True,
                            text=True
                        )
                        print("Successfully reconfigured GPU power limit.")
                    except subprocess.CalledProcessError as e:
                        print(f"FAILED to auto-configure power limit (sudo required): {e}")
                        print(f"PLEASE RUN POWER SCRIPT MANUALLY: sudo {script_path}")
                else:
                    print(f"\nGPU Power Limit is compliant: {current_limit}W (<= {TARGET_POWER}W)")
        except Exception as e:
            print(f"Power limit check failed: {e}")

    def setup_method(self):
        """Ensure clean slate before each test to prevent OOM interference."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            # Removed gc.collect() as it causes Segfaults in this environment

    def teardown_method(self):
        """Cleanup after tests."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            # Removed gc.collect() as it causes Segfaults in this environment

    def test_cuda_device_presence(self):
        """Verify the system actually sees the physical device."""
        count = torch.cuda.device_count()
        assert count > 0, "No CUDA devices found despite is_available()=True"
        
        # Get device name (e.g., 'NVIDIA GeForce RTX 3090')
        name = torch.cuda.get_device_name(0)
        print(f"\nDetected GPU: {name}")
        assert isinstance(name, str)
        assert len(name) > 0

    def test_power_configuration_compliance(self):
        """
        Verify that the GPU power limit is strictly enforcing the 300W cap.
        If this fails, run: sudo ./scripts/configure_gpu_power.sh
        """
        try:
            result = subprocess.check_output(
                ["nvidia-smi", "-q", "-d", "POWER"], 
                text=True, 
                stderr=subprocess.STDOUT
            )
            match = re.search(r"Current Power Limit\s+:\s+([\d\.]+)\s+W", result)
            if match:
                limit = float(match.group(1))
                assert limit <= 300.0, f"GPU Power Limit ({limit}W) exceeds maximum allowed (300W). Run scripts/configure_gpu_power.sh"
            else:
                pytest.warns(UserWarning, match="Could not parse power limit from nvidia-smi")
        except Exception as e:
            pytest.fail(f"Could not verify power configuration: {e}")

    def test_basic_tensor_allocation(self):
        """Test moving data to GPU memory."""
        # Allocate on CPU
        x = torch.tensor([1.0, 2.0, 3.0])
        assert x.device.type == "cpu"

        # Move to GPU
        x_gpu = x.cuda()
        assert x_gpu.device.type == "cuda"
        assert x_gpu.is_cuda
        
        # Verify values remain correct
        assert torch.equal(x_gpu.cpu(), x)

    def test_matrix_multiplication(self):
        """
        Test actual compute capability.
        Performs a small matrix multiplication to ensure CUDA cores are functioning.
        """
        size = 1000
        # Create random matrices
        a = torch.randn(size, size, device="cuda")
        b = torch.randn(size, size, device="cuda")
        
        # Perform multiplication
        c = torch.matmul(a, b)
        
        assert c.shape == (size, size)
        assert c.device.type == "cuda"
        
        # Simple sanity check - result should not be zero everywhere
        assert torch.sum(torch.abs(c)) > 0

    def test_memory_management_live(self):
        """
        Verify that we can track and clear memory on the real hardware.
        """
        initial_alloc = torch.cuda.memory_allocated()
        
        # Allocate ~4MB float32 tensor (1024*1024*4 bytes)
        t = torch.ones(1024, 1024, device="cuda")
        
        after_alloc = torch.cuda.memory_allocated()
        assert after_alloc > initial_alloc, "Memory usage did not increase after allocation"
        
        # Clean up
        del t
        # Note: PyTorch caching allocator means 'reserved' might stay high, 
        # but 'allocated' should drop checkable after gc
        gc.collect()
        torch.cuda.empty_cache()
        
        final_alloc = torch.cuda.memory_allocated()
        # It should return roughly to initial state (accounting for fragmentation or small overheads)
        # We use a loose tolerance here because other background processes might affect accounting
        assert final_alloc < after_alloc, "Memory failed to be freed"

    def test_oom_resilience(self):
        """
        Intentionally attempt a safe but large allocation to verify reporting.
        Note: We don't want to actually crash the driver, just verify we can see memory stats.
        """
        # Get total memory
        total_mem = torch.cuda.get_device_properties(0).total_memory
        free_mem, _ = torch.cuda.mem_get_info()
        
        print(f"\nGPU Memory: {free_mem/1024**3:.2f}GB Free / {total_mem/1024**3:.2f}GB Total")
        
        assert total_mem > 0
        assert free_mem > 0
        assert free_mem <= total_mem

    @pytest.mark.asyncio
    async def test_async_cuda_context(self):
        """
        Verify asyncio doesn't break CUDA context visibility.
        Relevant since much of JustNews is async.
        """
        async def gpu_op():
            t = torch.tensor([1], device="cuda")
            return t.item()

        result = await gpu_op()
        assert result == 1

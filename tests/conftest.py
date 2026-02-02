"""
Comprehensive Testing Framework for JustNews

This module provides a unified testing infrastructure that consolidates
 all testing patterns, fixtures, and utilities used across the JustNews
system. It follows clean repository patterns and provides production-ready
testing capabilities.

Key Features:
- Unified fixture management for all components
- Comprehensive mocking for external dependencies
- Async testing support with pytest-asyncio
- Performance testing utilities
- Integration testing helpers
- GPU testing capabilities
- Database testing fixtures
- Security testing utilities

Usage:
    pytest tests/refactor/ --cov=agents --cov-report=html
    pytest tests/refactor/ -m "gpu" --runslow
    pytest tests/refactor/ -k "integration"
"""

import asyncio
import os
import sys
import tempfile
import textwrap
import types
from pathlib import Path

import pytest
import pytest_asyncio

# Keep GPU orchestrator imports lightweight during pytest runs to avoid
# instantiating heavy services (MariaDB, Chroma, embedding models) during module import.
os.environ.setdefault("GPU_ORCHESTRATOR_SKIP_BOOTSTRAP", "1")
# Disable GPU-marked tests by default for safety (prevents accidental real GPU usage
# when running the full suite in a development environment). Developers who want
# to exercise real GPU behavior should explicitly opt in by setting
# TEST_GPU_AVAILABLE=true in their shell or CI job.
os.environ.setdefault("TEST_GPU_AVAILABLE", "false")
os.environ.setdefault("TEST_GPU_COUNT", "1")

# Add the repository root to sys.path so project packages import cleanly regardless
# of how pytest is launched (e.g. via `conda run`). The previous logic walked one
# directory too far up and missed the actual repo root, so imports like
# `common.observability` would fail when PYTHONPATH was not manually set.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

# Guarantee that a minimal testing global.env is present at import-time to
# avoid modules parsing /etc/justnews/global.env during collection. This is
# intentionally performed during import so early imports honor the test env.
if not os.environ.get("JUSTNEWS_GLOBAL_ENV"):
    early_tmp = Path(tempfile.gettempdir()) / f"justnews_test_global_env_{os.getpid()}"
    early_tmp.mkdir(parents=True, exist_ok=True)
    early_env = early_tmp / "global.env"
    if not early_env.exists():
        early_env.write_text(
            textwrap.dedent(f"""
        # Auto-generated early global.env for pytest import time
        SERVICE_DIR={project_root}
        PYTHON_BIN={os.environ.get("PYTHON_BIN", "")}
        JUSTNEWS_PYTHON={os.environ.get("JUSTNEWS_PYTHON", "")}
        MODEL_STORE_ROOT={project_root}/model_store
        MARIADB_HOST=127.0.0.1
        MARIADB_PORT=3306
        MARIADB_DB=justnews_test
        MARIADB_USER=justnews
        MARIADB_PASSWORD=test
        MARIADB_HOST=127.0.0.1
        MARIADB_PORT=3306
        MARIADB_DB=justnews_test
        MARIADB_USER=justnews
        MARIADB_PASSWORD=test
        """)
        )
    os.environ["JUSTNEWS_GLOBAL_ENV"] = str(early_env)

# Indicate we are running pytest; this affects how `common.env_loader` chooses
# whether to consult /etc/justnews/global.env. This helps keep test runs
# hermetic and not rely on the host's installed system files.
os.environ["PYTEST_RUNNING"] = "1"

def _detect_phase_from_path(interpreter_path: str) -> int | None:
    """Extract phase number from conda env path (e.g., .../justnews-py312-phase2 -> 2).
    
    Returns: 1-4 for phase envs, 1 for unified env (justnews-py312), None if not recognized.
    """
    try:
        env_name = os.path.basename(os.path.dirname(os.path.dirname(interpreter_path or "")))
        # Phase envs: justnews-py312-phase1, justnews-py312-phase2, etc.
        if "justnews-py312-phase" in env_name:
            phase_str = env_name.split("-phase")[-1]
            phase = int(phase_str)
            if 1 <= phase <= 4:
                return phase
        # Unified env: treat as phase 1 equivalent
        elif "justnews-py312" in env_name:
            return 1
    except (ValueError, IndexError, AttributeError):
        pass
    return None


# Enforce usage of the project's conda environment for local runs
# - In CI we allow broader environments (CI=true will skip the check)
# - Developers can temporarily bypass with ALLOW_ANY_PYTEST_ENV=1
if (
    os.environ.get("CI", "").lower() not in ("1", "true")
    and os.environ.get("ALLOW_ANY_PYTEST_ENV", "") != "1"
):
    # Detect phase from current interpreter path (supports both unified and phased envs)
    detected_phase = _detect_phase_from_path(sys.executable)
    
    if detected_phase is None:
        # Not running in a JustNews conda environment at all
        msg = """
Tests should be run inside a JustNews conda environment for consistent results.

Supported environments:
  - justnews-py312 (unified)
  - justnews-py312-phase1, -phase2, -phase3, -phase4 (phased)

To setup:
  bash scripts/dev/setup_dev_environment.sh --create-all-phases
  bash scripts/dev/select_phase_env.sh --phase 1
  source ./global.env

Then run tests:
  pytest tests/

If you intentionally want to run in a different environment set ALLOW_ANY_PYTEST_ENV=1 to bypass this check.
"""
        pytest.exit(msg)

# Import common utilities
from common.observability import get_logger  # noqa: E402

logger = get_logger(__name__)

# ============================================================================
# MOCKING INFRASTRUCTURE
# ============================================================================


class MockResponse:
    """Unified mock response for HTTP calls"""

    def __init__(
        self,
        status_code: int = 200,
        json_data: dict | None = None,
        text: str = "",
        headers: dict | None = None,
    ):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text
        self.headers = headers or {}

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise Exception(f"HTTP {self.status_code}: {self.text}")


def create_mock_torch() -> types.ModuleType:
    """Create comprehensive torch mock for testing"""

    class MockDevice:
        def __init__(self, spec: str):
            self.spec = str(spec)

        def __str__(self) -> str:
            return self.spec

        def __repr__(self) -> str:
            return f"device(type='{self.spec}')"

    class MockCuda:
        @staticmethod
        def is_available() -> bool:
            return os.environ.get("TEST_GPU_AVAILABLE", "false").lower() == "true"

        @staticmethod
        def device_count() -> int:
            return int(os.environ.get("TEST_GPU_COUNT", "0"))

        class Event:
            def __init__(self):
                self.recorded = False

            def record(self):
                self.recorded = True

            def synchronize(self):
                pass

            def elapsed_time(self, other):
                return 0.001

        # Additional minimal GPU helper methods used by tests
        @staticmethod
        def set_device(device_id: int) -> None:
            # No-op for tests
            return None

        @staticmethod
        def empty_cache() -> None:
            # No-op for tests
            return None

        @staticmethod
        def mem_get_info(device_id: int) -> tuple[int, int]:
            # Return (free, total) in bytes — default to 8GB free, 12GB total
            return (8 * 1024 * 1024 * 1024, 12 * 1024 * 1024 * 1024)

        @staticmethod
        def memory_allocated(device_id: int = 0) -> int:
            return 1024 * 1024 * 1024  # 1GB

        @staticmethod
        def memory_reserved(device_id: int = 0) -> int:
            return 2 * 1024 * 1024 * 1024  # 2GB

        @staticmethod
        def memory_summary(*args, **kwargs) -> str:
            return "Mock memory summary"

        @staticmethod
        def synchronize(device_id: int = 0) -> None:
            # No-op in mock
            return None

        @staticmethod
        def device(spec):
            # Allow patching "torch.cuda.device" target used in tests
            return MockDevice(spec)

    fake_torch = types.ModuleType("torch")

    # Core torch attributes
    fake_torch.device = lambda s: MockDevice(s)
    fake_torch.cuda = MockCuda()

    # Data types
    fake_torch.float32 = object()
    fake_torch.float16 = object()
    fake_torch.int64 = object()
    fake_torch.bool = object()

    # Tensor operations
    class MockTensor:
        def __init__(self, data=None, dtype=None, device=None):
            self.data = data
            self.dtype = dtype
            self.device = device or MockDevice("cpu")

        def to(self, device):
            return MockTensor(self.data, self.dtype, device)

        def cpu(self):
            return MockTensor(self.data, self.dtype, MockDevice("cpu"))

        def cuda(self):
            return MockTensor(self.data, self.dtype, MockDevice("cuda"))

        def detach(self):
            return self

        def numpy(self):
            return self.data if self.data is not None else []

        def item(self):
            return self.data if isinstance(self.data, (int, float)) else 0

        def __getitem__(self, key):
            return MockTensor()

        def __len__(self):
            return len(self.data) if hasattr(self.data, "__len__") else 1

    fake_torch.tensor = lambda data, **kwargs: MockTensor(data, **kwargs)
    fake_torch.zeros = lambda *args, **kwargs: MockTensor()
    fake_torch.ones = lambda *args, **kwargs: MockTensor()
    fake_torch.randn = lambda *args, **kwargs: MockTensor()
    fake_torch.Tensor = MockTensor

    # Neural network modules
    class MockModule:
        def __init__(self):
            self.training = True

        def eval(self):
            self.training = False
            return self

        def train(self):
            self.training = True
            return self

        def to(self, device):
            return self

        def __call__(self, *args, **kwargs):
            return MockTensor()

    class MockLinear(MockModule):
        def __init__(self, in_features, out_features):
            super().__init__()
            self.in_features = in_features
            self.out_features = out_features

    fake_torch.nn = types.SimpleNamespace(
        Module=MockModule,
        Linear=MockLinear,
        Embedding=MockModule,
        LayerNorm=MockModule,
        Dropout=MockModule,
        MSELoss=lambda: MockModule(),
        CrossEntropyLoss=lambda: MockModule(),
        BCEWithLogitsLoss=lambda: MockModule(),
    )

    # Optimization
    class MockOptimizer:
        def __init__(self, params, lr=0.001):
            self.param_groups = [{"lr": lr, "params": params}]

        def step(self):
            pass

        def zero_grad(self):
            pass

    fake_torch.optim = types.SimpleNamespace(
        Adam=lambda params, **kwargs: MockOptimizer(params, **kwargs),
        SGD=lambda params, **kwargs: MockOptimizer(params, **kwargs),
        AdamW=lambda params, **kwargs: MockOptimizer(params, **kwargs),
    )

    return fake_torch


def create_mock_transformers() -> types.ModuleType:
    """Create comprehensive transformers mock"""

    fake_transformers = types.ModuleType("transformers")

    class MockTokenizer:
        def __init__(self):
            self.vocab_size = 30000
            self.pad_token_id = 0
            self.eos_token_id = 2
            self.bos_token_id = 1

        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

        def __call__(self, texts, **kwargs):
            if isinstance(texts, str):
                texts = [texts]
            batch_size = len(texts)
            max_length = kwargs.get("max_length", 128)
            return {
                "input_ids": [[1] * max_length for _ in range(batch_size)],
                "attention_mask": [[1] * max_length for _ in range(batch_size)],
            }

        def decode(self, tokens, **kwargs):
            return "mock decoded text"

        def encode(self, text, **kwargs):
            return [1, 2, 3, 2]

    class MockModel:
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()

        def __call__(self, **kwargs):
            return types.SimpleNamespace(
                last_hidden_state=[
                    [0.1] * 768
                    for _ in range(kwargs.get("input_ids", [[1]])[0].__len__())
                ],
                pooler_output=[0.1] * 768,
            )

    fake_transformers.AutoTokenizer = MockTokenizer
    fake_transformers.AutoModel = MockModel
    fake_transformers.AutoModelForSequenceClassification = MockModel
    fake_transformers.AutoModelForCausalLM = MockModel
    fake_transformers.AutoModelForTokenClassification = MockModel
    fake_transformers.BertModel = MockModel
    fake_transformers.BertTokenizer = MockTokenizer
    fake_transformers.pipeline = lambda task, **kwargs: lambda text: {
        "label": "POSITIVE",
        "score": 0.9,
    }

    return fake_transformers


def create_mock_sentence_transformers() -> types.ModuleType:
    """Create sentence transformers mock"""

    fake_st = types.ModuleType("sentence_transformers")

    class MockSentenceTransformer:
        def __init__(self, model_name=None):
            self.model_name = model_name or "mock-model"

        def encode(self, sentences, **kwargs):
            if isinstance(sentences, str):
                return [0.1] * 384
            return [[0.1] * 384 for _ in sentences]

    fake_st.SentenceTransformer = MockSentenceTransformer
    return fake_st


def create_mock_requests() -> types.ModuleType:
    """Create requests mock with MCP Bus compatibility"""

    fake_requests = types.ModuleType("requests")

    def mock_get(url, **kwargs):
        # MCP Bus endpoints
        if "/agents" in url:
            return MockResponse(
                200,
                {
                    "analyst": "http://localhost:8004",
                    "fact_checker": "http://localhost:8003",
                    "synthesizer": "http://localhost:8005",
                    # "scout": "http://localhost:8002", (Deprecated)
                    "critic": "http://localhost:8006",
                    "memory": "http://localhost:8007",
                    "reasoning": "http://localhost:8008",
                    "chief_editor": "http://localhost:8001",
                },
            )
        elif "/health" in url:
            return MockResponse(200, {"status": "healthy"})
        elif "vector_search" in url:
            return MockResponse(200, [])
        elif "/get_article/" in url:
            return MockResponse(
                200,
                {
                    "id": "test-article-123",
                    "content": "Test article content for testing purposes.",
                    "meta": {"source": "test", "timestamp": "2024-01-01T00:00:00Z"},
                },
            )
        return MockResponse(200, {})

    def mock_post(url, **kwargs):
        if "vector_search" in url:
            return MockResponse(200, [])
        elif url.endswith("/call"):
            return MockResponse(200, {"status": "success", "data": {}})
        elif "/log_training_example" in url:
            return MockResponse(200, {"status": "logged"})
        return MockResponse(200, {})

    fake_requests.get = mock_get
    fake_requests.post = mock_post
    fake_requests.exceptions = types.SimpleNamespace(
        RequestException=Exception, Timeout=Exception, ConnectionError=Exception
    )

    return fake_requests


# ============================================================================
# GLOBAL FIXTURES
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup comprehensive test environment with all mocks"""

    # Install mocks if not in real environment
    if not os.environ.get("USE_REAL_ML_LIBS"):
        # Mock heavy ML libraries
        if "torch" not in sys.modules:
            sys.modules["torch"] = create_mock_torch()
        if "transformers" not in sys.modules:
            sys.modules["transformers"] = create_mock_transformers()
        if "sentence_transformers" not in sys.modules:
            sys.modules["sentence_transformers"] = create_mock_sentence_transformers()

    # Mock requests for HTTP calls
    if "requests" not in sys.modules and not os.environ.get("USE_REAL_REQUESTS"):
        sys.modules["requests"] = create_mock_requests()

    # Mock chromadb to avoid importing optional telemetry-heavy SDK during tests
    if "chromadb" not in sys.modules and not os.environ.get("USE_REAL_CHROMADB"):
        fake_chromadb = types.ModuleType("chromadb")

        class FakeHttpClient:
            def __init__(self, host=None, port=None, tenant=None):
                self.host = host
                self.port = port
                self.tenant = tenant

            def heartbeat(self):
                return True

            def list_collections(self):
                return []

            def get_collection(self, name):
                return types.SimpleNamespace(name=name)

        fake_chromadb.HttpClient = FakeHttpClient
        # telemetry module stub
        fake_chromadb.telemetry = types.SimpleNamespace(
            opentelemetry=types.SimpleNamespace()
        )
        sys.modules["chromadb"] = fake_chromadb

    yield

    # Cleanup if needed
    pass


@pytest.fixture(scope="session", autouse=True)
def create_test_global_env(tmp_path_factory):
    """Create a temporary global.env for tests and set JUSTNEWS_GLOBAL_ENV.

    This avoids relying on /etc/justnews/global.env for tests and ensures a
    deterministic environment for test discovery and configuration.
    """
    # Preserve any existing override and restore afterwards
    prev = os.environ.get("JUSTNEWS_GLOBAL_ENV")
    # Build a minimal, safe test global.env in a temp directory
    tmp_dir = tmp_path_factory.mktemp("global_env")
    path = tmp_dir / "global.env"
    contents = textwrap.dedent(f"""
    # Auto-generated test global.env
    SERVICE_DIR={project_root}
    PYTHON_BIN={os.environ.get("PYTHON_BIN", "")}
    JUSTNEWS_PYTHON={os.environ.get("JUSTNEWS_PYTHON", "")}
    MODEL_STORE_ROOT={project_root}/model_store
    MARIADB_HOST=127.0.0.1
    MARIADB_PORT=3306
    MARIADB_DB=justnews_test
    MARIADB_USER=justnews
    MARIADB_PASSWORD=test
    """)
    path.write_text(contents, encoding="utf-8")
    os.environ["JUSTNEWS_GLOBAL_ENV"] = str(path)

    # Also ensure SERVICE_DIR visible to modules that inspect it directly
    os.environ.setdefault("SERVICE_DIR", str(project_root))

    yield path

    # Cleanup - restore previous env var if any
    if prev is not None:
        os.environ["JUSTNEWS_GLOBAL_ENV"] = prev
    else:
        os.environ.pop("JUSTNEWS_GLOBAL_ENV", None)


@pytest.fixture(scope="session")
def event_loop_policy():
    """Configure event loop policy for async tests"""
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture(scope="function")
async def async_setup():
    """Base async fixture for all async tests"""
    yield


# ============================================================================
# AGENT TESTING FIXTURES
# ============================================================================


@pytest.fixture
def sample_articles():
    """Provide sample articles for testing"""
    return [
        {
            "id": "article-1",
            "content": "This is a positive news article about technology advancements.",
            "meta": {"source": "tech-news", "sentiment": "positive"},
        },
        {
            "id": "article-2",
            "content": "Breaking news: Market shows significant growth today.",
            "meta": {"source": "finance-news", "sentiment": "positive"},
        },
        {
            "id": "article-3",
            "content": "Concerns raised about environmental impact of new policy.",
            "meta": {"source": "environment-news", "sentiment": "negative"},
        },
    ]


@pytest.fixture
def mock_mcp_bus_response():
    """Mock MCP Bus response for agent communication"""
    return {
        "status": "success",
        "data": {
            "result": "mock analysis result",
            "confidence": 0.85,
            "metadata": {"processing_time": 0.1},
        },
    }


@pytest.fixture
def mock_gpu_context():
    """Mock GPU context for GPU-dependent tests"""

    class MockGPUContext:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def allocate_memory(self, size):
            return f"mock_gpu_memory_{size}"

        def free_memory(self, memory):
            pass

    return MockGPUContext()


# ============================================================================
# DATABASE TESTING FIXTURES
# ============================================================================


@pytest.fixture
def mock_database_connection():
    """Mock database connection for testing"""

    class MockConnection:
        def __init__(self):
            self.connected = True
            self.transactions = []

        async def execute(self, query, *args):
            self.transactions.append({"query": query, "args": args})
            return MockResult()

        async def fetch(self, query, *args):
            return [
                {"id": 1, "content": "mock article", "meta": {}},
                {"id": 2, "content": "another mock article", "meta": {}},
            ]

        async def close(self):
            self.connected = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            await self.close()

    class MockResult:
        def __init__(self):
            self.rowcount = 1

    return MockConnection()


# ============================================================================
# PERFORMANCE TESTING UTILITIES
# ============================================================================


@pytest.fixture
def performance_timer():
    """Timer fixture for performance testing"""

    class PerformanceTimer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = asyncio.get_event_loop().time()

        def stop(self):
            self.end_time = asyncio.get_event_loop().time()

        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return 0

        def assert_under_limit(self, limit_seconds, operation_name="operation"):
            elapsed = self.elapsed
            assert elapsed < limit_seconds, (
                f"{operation_name} took {elapsed:.3f}s, limit was {limit_seconds}s"
            )

    return PerformanceTimer()


# ============================================================================
# SECURITY TESTING FIXTURES
# ============================================================================


@pytest.fixture
def mock_security_context():
    """Mock security context for testing"""

    class MockSecurityContext:
        def __init__(self):
            self.user_id = "test-user-123"
            self.permissions = ["read", "write", "analyze"]
            self.token_valid = True

        def validate_token(self, token):
            return self.token_valid

        def has_permission(self, permission):
            return permission in self.permissions

        def encrypt_data(self, data):
            return f"encrypted_{data}"

        def decrypt_data(self, encrypted_data):
            if encrypted_data.startswith("encrypted_"):
                return encrypted_data[10:]
            return encrypted_data

    return MockSecurityContext()


# ============================================================================
# CONFIGURATION TESTING FIXTURES
# ============================================================================


@pytest.fixture
def test_config():
    """Test configuration fixture"""
    return {
        "database": {
            "url": "mysql://test:test@localhost:3306/test_db",
            "pool_size": 5,
            "timeout": 30,
        },
        "mcp_bus": {"url": "http://localhost:8000", "timeout": 10, "retries": 3},
        "gpu": {"enabled": False, "memory_limit": "2GB", "devices": []},
        "logging": {"level": "INFO", "format": "json"},
    }


# ============================================================================
# MARKERS AND CONFIGURATION
# ============================================================================


def pytest_addoption(parser):
    """Add custom command line options"""
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line("markers", "gpu: marks tests that require GPU")
    config.addinivalue_line("markers", "slow: marks tests that are slow")
    config.addinivalue_line("markers", "integration: marks integration tests")
    config.addinivalue_line("markers", "security: marks security-related tests")
    config.addinivalue_line("markers", "performance: marks performance tests")
    config.addinivalue_line("markers", "database: marks database tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection based on environment"""

    # Skip GPU tests if no GPU available
    gpu_available = os.environ.get("TEST_GPU_AVAILABLE", "false").lower() == "true"
    if not gpu_available:
        skip_gpu = pytest.mark.skip(reason="GPU not available")
        for item in items:
            if "gpu" in item.keywords:
                item.add_marker(skip_gpu)

    # Skip slow tests unless explicitly requested
    try:
        runslow = config.getoption("--runslow", default=False)
    except ValueError:
        runslow = False

    if not runslow:
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def assert_async_operation_completes_within(async_func, timeout_seconds=5.0):
    """Assert that an async operation completes within timeout"""

    async def run_with_timeout():
        try:
            await asyncio.wait_for(async_func(), timeout=timeout_seconds)
            return True
        except TimeoutError:
            return False

    result = asyncio.run(run_with_timeout())
    assert result, f"Async operation did not complete within {timeout_seconds} seconds"


def create_mock_agent_response(agent_name, tool_name, result=None, error=None):
    """Create standardized mock agent response"""
    return {
        "agent": agent_name,
        "tool": tool_name,
        "result": result,
        "error": error,
        "timestamp": "2024-01-01T00:00:00Z",
        "processing_time": 0.1,
    }


def parametrize_test_data(*test_cases):
    """Helper to parametrize test data"""
    return pytest.mark.parametrize(
        "test_input,expected_output",
        test_cases,
        ids=[f"case_{i}" for i in range(len(test_cases))],
    )

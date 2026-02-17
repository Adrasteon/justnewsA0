# Database Refactor Tests - Configuration and Fixtures

import os
from unittest.mock import Mock, patch

import pytest

from database.core.backup_manager import BackupManager
from database.core.migration_engine import MigrationEngine
from database.core.query_optimizer import QueryOptimizer
from database.core.schema_manager import SchemaManager
from database.models.base_model import BaseModel
from database.utils.database_utils import get_db_config


@pytest.fixture
def mock_db_config():
    """Mock database configuration for testing"""
    return {
        "host": "localhost",
        "port": 3306,
        "database": "test_db",
        "user": "test_user",
        "password": "test_password",
        "min_connections": 1,
        "max_connections": 5,
        "health_check_interval": 30,
        "max_retries": 3,
        "retry_delay": 1.0,
    }


@pytest.fixture
def mock_connection():
    """Mock database connection"""
    conn = Mock()
    conn.cursor.return_value.__enter__ = Mock()
    conn.cursor.return_value.__exit__ = Mock()
    conn.close = Mock()
    return conn


@pytest.fixture
def mock_pool(mock_db_config):
    """Mock connection pool"""
    # This module previously mocked psycopg2 (Postgres) behavior. Since
    # Postgres is deprecated, rely on MySQL/MariaDB mocks for tests and
    # avoid importing psycopg2-related things here. The migrated service and
    # DatabaseConnectionPool now exclusively target MariaDB.
    with (
        patch("mysql.connector.connect"),
        patch(
            "database.core.connection_pool.create_database_service"
        ) as mock_create_service,
        patch("database.core.connection_pool.get_db_config") as mock_get_db_config,
    ):
        from database.core.connection_pool import DatabaseConnectionPool

        # Provide deterministic config for the pool initialization
        mock_get_db_config.return_value = {
            "mariadb": {
                "host": "localhost",
                "port": 3306,
                "database": "test_db",
                "user": "test_user",
                "password": "test_password",
            },
            "connection_pool": {
                "min_connections": 1,
                "max_connections": 5,
                "health_check_interval": 30,
                "max_retries": 3,
                "retry_delay": 1.0,
                "connection_timeout_seconds": 3.0,
                "command_timeout_seconds": 30.0,
            },
            "chromadb": {"host": "localhost", "port": 3307, "collection": "articles"},
            "embedding": {
                "model": "all-MiniLM-L6-v2",
                "dimensions": 384,
                "device": "cpu",
            },
        }

        mock_service = Mock()
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.execute = Mock()
        mock_cursor.fetchone = Mock(return_value=(1,))
        mock_cursor.fetchall = Mock(return_value=[])
        mock_cursor.close = Mock()
        mock_connection.cursor.return_value = mock_cursor
        mock_connection.rollback = Mock()
        mock_connection.commit = Mock()
        mock_service.mb_conn = mock_connection
        mock_create_service.return_value = mock_service

        pool = DatabaseConnectionPool(mock_db_config)

        # Mock the execute_query method (individual tests stub behavior as needed)
        pool.execute_query = Mock()

        # Mock the get_metrics method
        pool.get_metrics = Mock(return_value={"connections_created": 5})

        # Mock the get_connection method to return a context manager
        mock_context = Mock()
        mock_context.__enter__ = Mock(return_value=Mock())
        mock_context.__exit__ = Mock(return_value=None)
        pool.get_connection = Mock(return_value=mock_context)

        yield pool


@pytest.fixture
def mock_schema_manager(mock_pool):
    """Mock schema manager"""
    return SchemaManager(mock_pool)


@pytest.fixture
def mock_migration_engine(mock_pool):
    """Mock migration engine"""
    return MigrationEngine(mock_pool)


@pytest.fixture
def mock_query_optimizer(mock_pool):
    """Mock query optimizer"""
    return QueryOptimizer(mock_pool)


@pytest.fixture
def mock_backup_manager(mock_pool):
    """Mock backup manager"""
    backup_config = {"backup_dir": "/tmp/test_backups", "storage_backends": []}
    return BackupManager(mock_pool, backup_config)


@pytest.fixture
def mock_base_model(mock_pool):
    """Mock base model setup"""
    BaseModel.set_connection_pool(mock_pool)
    yield BaseModel
    # Reset after test
    BaseModel._connection_pool = None


@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock environment variables for testing"""
    env_vars = {
        "MARIADB_HOST": "localhost",
        "MARIADB_PORT": "3306",
        "MARIADB_DB": "test_db",
        "MARIADB_USER": "test_user",
        "MARIADB_PASSWORD": "test_password",
        "DB_MIN_CONNECTIONS": "1",
        "DB_MAX_CONNECTIONS": "5",
        "DB_HEALTH_CHECK_INTERVAL": "30",
        "DB_MAX_RETRIES": "3",
        "DB_RETRY_DELAY": "1.0",
    }

    # Ensure that no external DATABASE_URL or Postgres envvars from the
    # developer's environment can override the explicit MariaDB testing
    # values. We don't clear the whole environment because other test
    # helpers (e.g. PYTEST_RUNNING) are provided by the top-level
    # conftest; just remove keys that could shadow the explicit values
    # above and make the tests deterministic.
    with patch.dict(os.environ, env_vars):
        # Remove any global/outer overrides which would otherwise take
        # precedence (DATABASE_URL, Postgres envvars).  This makes the
        # tests deterministic regardless of a developer's shell env.
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("POSTGRES_DB", None)
        os.environ.pop("POSTGRES_HOST", None)
        os.environ.pop("POSTGRES_USER", None)
        os.environ.pop("POSTGRES_PASSWORD", None)
        yield


@pytest.fixture
def test_db_config():
    """Get test database configuration"""
    return get_db_config()

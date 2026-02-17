"""
JustNews Database Layer - Advanced Implementation
Enterprise-grade database layer with connection pooling, migrations, and performance optimization

Features:
- Advanced Connection Pooling: Optimized database connections with health monitoring
- Schema Management: Automated schema versioning and migrations with rollback
- Performance Optimization: Query optimization, caching, and monitoring
- Backup & Recovery: Automated backup and disaster recovery procedures
- Multi-Database Support: Support for PostgreSQL, MySQL, SQLite backends
- Monitoring Integration: Database metrics and health monitoring
"""

from .core.backup_manager import BackupManager
from .core.connection_pool import DatabaseConnectionPool
from .core.migration_engine import MigrationEngine
from .core.query_optimizer import QueryOptimizer
from .core.schema_manager import SchemaManager
from .models.base_model import BaseModel
from .utils.database_utils import (
    execute_query_async,
    execute_transaction,
    get_db_config,
)

__all__ = [
    "DatabaseConnectionPool",
    "SchemaManager",
    "MigrationEngine",
    "QueryOptimizer",
    "BackupManager",
    "BaseModel",
    "get_db_config",
    "execute_query_async",
    "execute_transaction",
]

# Version information
__version__ = "1.0.0"
__author__ = "JustNews Development Team"

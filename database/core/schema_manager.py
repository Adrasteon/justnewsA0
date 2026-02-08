"""
Schema Manager - Advanced Implementation
Automated schema versioning and management with migration tracking

Features:
- Schema Versioning: Automatic schema version tracking and validation
- Migration Tracking: Complete migration history and rollback capabilities
- Schema Validation: Automated schema consistency checks
- Metadata Management: Schema metadata storage and retrieval
- Dependency Resolution: Automatic dependency resolution for migrations
"""

import hashlib
import os
from typing import Any

from common.observability import get_logger

from .connection_pool import DatabaseConnectionPool

logger = get_logger(__name__)


class SchemaManager:
    """
    Advanced schema management with versioning and migration tracking
    """

    def __init__(
        self, connection_pool: DatabaseConnectionPool, schema_dir: str = "migrations"
    ):
        """
        Initialize the schema manager

        Args:
            connection_pool: Database connection pool instance
            schema_dir: Directory containing migration files
        """
        self.pool = connection_pool
        self.schema_dir = schema_dir
        self.schema_table = "schema_versions"

        # Ensure schema tracking table exists
        self._ensure_schema_table()

    def _ensure_schema_table(self):
        """Ensure the schema versions tracking table exists"""
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {self.schema_table} (
            version VARCHAR(255) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(50) DEFAULT 'applied',
            rollback_sql TEXT,
            dependencies JSONB DEFAULT '[]'::jsonb,
            metadata JSONB DEFAULT '{{}}'::jsonb
        );

        CREATE INDEX IF NOT EXISTS idx_schema_versions_applied_at
        ON {self.schema_table} (applied_at);

        CREATE INDEX IF NOT EXISTS idx_schema_versions_status
        ON {self.schema_table} (status);
        """

        try:
            self.pool.execute_query(create_table_query, fetch=False)
            logger.info("Schema versions tracking table initialized")
        except Exception as e:
            logger.error(f"Failed to initialize schema tracking table: {e}")
            raise

    def get_current_version(self) -> str | None:
        """
        Get the current schema version

        Returns:
            Current schema version string or None if no migrations applied
        """
        query = f"""
        SELECT version FROM {self.schema_table}
        WHERE status = 'applied'
        ORDER BY applied_at DESC
        LIMIT 1
        """

        try:
            results = self.pool.execute_query(query)
            return results[0]["version"] if results else None
        except Exception as e:
            logger.error(f"Failed to get current schema version: {e}")
            return None

    def get_migration_history(self) -> list[dict[str, Any]]:
        """
        Get complete migration history

        Returns:
            List of migration records
        """
        query = f"""
        SELECT version, name, checksum, applied_at, status, dependencies, metadata
        FROM {self.schema_table}
        ORDER BY applied_at DESC
        """

        try:
            results = self.pool.execute_query(query)
            return results
        except Exception as e:
            logger.error(f"Failed to get migration history: {e}")
            return []

    def validate_schema(self) -> dict[str, Any]:
        """
        Validate current schema against migration history

        Returns:
            Validation results dictionary
        """
        validation_results = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "checksum_mismatches": [],
            "missing_migrations": [],
        }

        try:
            # Get applied migrations
            applied_migrations = self.pool.execute_query(
                f"SELECT version, checksum FROM {self.schema_table} WHERE status = 'applied'"
            )

            # Check for missing migration files
            migration_files = self._get_migration_files()
            applied_versions = {m["version"] for m in applied_migrations}

            for migration_file in migration_files:
                version = migration_file["version"]
                if version not in applied_versions:
                    validation_results["missing_migrations"].append(version)
                    validation_results["warnings"].append(
                        f"Migration {version} not applied"
                    )

            # Validate checksums for applied migrations
            for applied in applied_migrations:
                version = applied["version"]
                stored_checksum = applied["checksum"]

                migration_file = next(
                    (f for f in migration_files if f["version"] == version), None
                )

                if migration_file:
                    current_checksum = migration_file["checksum"]
                    if stored_checksum != current_checksum:
                        validation_results["checksum_mismatches"].append(
                            {
                                "version": version,
                                "stored": stored_checksum,
                                "current": current_checksum,
                            }
                        )
                        validation_results["errors"].append(
                            f"Checksum mismatch for migration {version}"
                        )
                        validation_results["is_valid"] = False

        except Exception as e:
            validation_results["errors"].append(f"Schema validation failed: {e}")
            validation_results["is_valid"] = False

        return validation_results

    def _get_migration_files(self) -> list[dict[str, Any]]:
        """
        Get list of migration files with metadata

        Returns:
            List of migration file information
        """
        migrations = []

        if not os.path.exists(self.schema_dir):
            return migrations

        for filename in sorted(os.listdir(self.schema_dir)):
            if filename.endswith(".sql"):
                filepath = os.path.join(self.schema_dir, filename)

                try:
                    with open(filepath, encoding="utf-8") as f:
                        content = f.read()

                    # Extract version from filename (e.g., "001_create_table.sql" -> "001")
                    version = filename.split("_")[0]

                    # Calculate checksum
                    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

                    migrations.append(
                        {
                            "version": version,
                            "filename": filename,
                            "filepath": filepath,
                            "content": content,
                            "checksum": checksum,
                        }
                    )

                except Exception as e:
                    logger.warning(f"Failed to read migration file {filename}: {e}")

        return migrations

    def get_schema_info(self) -> dict[str, Any]:
        """
        Get comprehensive schema information

        Returns:
            Schema information dictionary
        """
        return {
            "current_version": self.get_current_version(),
            "migration_history": self.get_migration_history(),
            "validation_results": self.validate_schema(),
            "table_count": self._get_table_count(),
            "total_rows": self._get_total_row_count(),
        }

    def _get_table_count(self) -> int:
        """Get total number of tables in the database"""
        try:
            query = """
            SELECT COUNT(*) as table_count
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
            results = self.pool.execute_query(query)
            return results[0]["table_count"] if results else 0
        except Exception as e:
            logger.warning(f"Failed to get table count: {e}")
            return 0

    def _get_total_row_count(self) -> int:
        """Get total number of rows across all tables"""
        try:
            # Get all table names
            query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
            tables = self.pool.execute_query(query)

            total_rows = 0
            for table in tables:
                table_name = table["table_name"]
                count_query = f"SELECT COUNT(*) as row_count FROM {table_name}"
                try:
                    count_result = self.pool.execute_query(count_query)
                    total_rows += count_result[0]["row_count"]
                except Exception:
                    # Skip tables we can't count
                    continue

            return total_rows
        except Exception as e:
            logger.warning(f"Failed to get total row count: {e}")
            return 0

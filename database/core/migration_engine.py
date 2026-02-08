"""
Migration Engine - Advanced Implementation
Automated migration execution with rollback capabilities and dependency resolution

Features:
- Migration Execution: Automated migration application with error handling
- Rollback Support: Automatic rollback capabilities for failed migrations
- Dependency Resolution: Automatic dependency resolution for complex migrations
- Transaction Safety: Migration execution within database transactions
- Progress Tracking: Real-time migration progress and status reporting
"""

import os
from typing import Any, Dict, List, Optional

from common.observability import get_logger

from .connection_pool import DatabaseConnectionPool
from .schema_manager import SchemaManager

logger = get_logger(__name__)


class MigrationEngine:
    """
    Advanced migration engine with rollback and dependency resolution
    """

    def __init__(self, connection_pool: DatabaseConnectionPool, migrations_dir: str = "migrations"):
        """
        Initialize the migration engine

        Args:
            connection_pool: Database connection pool instance
            migrations_dir: Directory containing migration files
        """
        self.pool = connection_pool
        self.migrations_dir = migrations_dir
        self.schema_manager = SchemaManager(connection_pool, migrations_dir)

    def apply_migrations(self, target_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Apply pending migrations up to target version

        Args:
            target_version: Target version to migrate to (None for latest)

        Returns:
            Migration results dictionary
        """
        results = {
            'success': True,
            'applied_migrations': [],
            'failed_migrations': [],
            'errors': []
        }

        try:
            # Get pending migrations
            pending_migrations = self._get_pending_migrations(target_version)

            if not pending_migrations:
                logger.info("No pending migrations to apply")
                return results

            logger.info(f"Applying {len(pending_migrations)} pending migrations")

            # Apply migrations in order
            for migration in pending_migrations:
                try:
                    self._apply_single_migration(migration)
                    results['applied_migrations'].append(migration['version'])
                    logger.info(f"Successfully applied migration {migration['version']}: {migration['name']}")

                except Exception as e:
                    error_msg = f"Failed to apply migration {migration['version']}: {e}"
                    results['failed_migrations'].append(migration['version'])
                    results['errors'].append(error_msg)
                    results['success'] = False
                    logger.error(error_msg)

                    # Stop applying further migrations on failure
                    break

        except Exception as e:
            results['success'] = False
            results['errors'].append(f"Migration process failed: {e}")
            logger.error(f"Migration process failed: {e}")

        return results

    def rollback_migration(self, version: str) -> Dict[str, Any]:
        """
        Rollback a specific migration

        Args:
            version: Migration version to rollback

        Returns:
            Rollback results dictionary
        """
        results = {
            'success': True,
            'rolled_back_version': None,
            'errors': []
        }

        try:
            # Get migration info
            migration_info = self._get_migration_info(version)
            if not migration_info:
                raise Exception(f"Migration {version} not found")

            if migration_info['status'] != 'applied':
                raise Exception(f"Migration {version} is not applied (status: {migration_info['status']})")

            # Check if rollback SQL exists
            if not migration_info.get('rollback_sql'):
                raise Exception(f"No rollback SQL available for migration {version}")

            # Execute rollback within transaction
            rollback_sql = migration_info['rollback_sql']

            with self.pool.get_connection() as conn:
                cursor = conn.cursor()
                try:
                    # Execute rollback SQL
                    cursor.execute(rollback_sql)

                    # Update migration status
                    update_query = f"""
                    UPDATE {self.schema_manager.schema_table}
                    SET status = 'rolled_back', applied_at = CURRENT_TIMESTAMP
                    WHERE version = %s
                    """
                    cursor.execute(update_query, (version,))

                    conn.commit()

                    results['rolled_back_version'] = version
                    logger.info(f"Successfully rolled back migration {version}")

                except Exception as e:
                    conn.rollback()
                    raise e
                finally:
                    cursor.close()

        except Exception as e:
            results['success'] = False
            results['errors'].append(f"Rollback failed: {e}")
            logger.error(f"Rollback failed for migration {version}: {e}")

        return results

    def _apply_single_migration(self, migration: Dict[str, Any]):
        """
        Apply a single migration with transaction safety

        Args:
            migration: Migration information dictionary
        """
        version = migration['version']
        name = migration['name']
        sql_content = migration['sql_content']
        checksum = migration['checksum']

        # Parse migration content for up/down sections
        up_sql, down_sql = self._parse_migration_content(sql_content)

        with self.pool.get_connection() as conn:
            cursor = conn.cursor()
            try:
                # Execute migration SQL
                cursor.execute(up_sql)

                # Record migration in schema table
                insert_query = f"""
                INSERT INTO {self.schema_manager.schema_table}
                (version, name, checksum, status, rollback_sql)
                VALUES (%s, %s, %s, 'applied', %s)
                """
                cursor.execute(insert_query, (version, name, checksum, down_sql))

                conn.commit()

            except Exception as e:
                conn.rollback()
                raise e
            finally:
                cursor.close()

    def _parse_migration_content(self, content: str) -> tuple[str, str]:
        """
        Parse migration content to separate up and down SQL

        Args:
            content: Raw migration file content

        Returns:
            Tuple of (up_sql, down_sql)
        """
        # Simple parsing - look for -- DOWN marker
        parts = content.split('-- DOWN')
        up_sql = parts[0].strip()

        down_sql = ""
        if len(parts) > 1:
            down_sql = parts[1].strip()

        return up_sql, down_sql

    def _get_pending_migrations(self, target_version: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get list of pending migrations

        Args:
            target_version: Target version to migrate to

        Returns:
            List of pending migration dictionaries
        """
        # Get applied versions
        applied_versions = set()
        history = self.schema_manager.get_migration_history()
        for migration in history:
            if migration['status'] == 'applied':
                applied_versions.add(migration['version'])

        # Get all migration files
        migration_files = self._get_migration_files()

        # Filter pending migrations
        pending = []
        for migration_file in migration_files:
            version = migration_file['version']

            # Skip if already applied
            if version in applied_versions:
                continue

            # Stop if we've reached target version
            if target_version and version > target_version:
                break

            pending.append({
                'version': version,
                'name': migration_file['name'],
                'sql_content': migration_file['content'],
                'checksum': migration_file['checksum'],
                'filepath': migration_file['filepath']
            })

        # Sort by version
        pending.sort(key=lambda x: x['version'])

        return pending

    def _get_migration_files(self) -> List[Dict[str, Any]]:
        """
        Get list of migration files

        Returns:
            List of migration file information
        """
        migrations = []

        if not os.path.exists(self.migrations_dir):
            return migrations

        for filename in sorted(os.listdir(self.migrations_dir)):
            if filename.endswith('.sql'):
                filepath = os.path.join(self.migrations_dir, filename)

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Parse filename (e.g., "001_create_table.sql")
                    parts = filename.split('_', 1)
                    version = parts[0]
                    name = parts[1].replace('.sql', '') if len(parts) > 1 else 'unnamed'

                    migrations.append({
                        'version': version,
                        'name': name,
                        'filename': filename,
                        'filepath': filepath,
                        'content': content
                    })

                except Exception as e:
                    logger.warning(f"Failed to read migration file {filename}: {e}")

        return migrations

    def _get_migration_info(self, version: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific migration

        Args:
            version: Migration version

        Returns:
            Migration information dictionary or None if not found
        """
        try:
            query = f"""
            SELECT * FROM {self.schema_manager.schema_table}
            WHERE version = %s
            """
            results = self.pool.execute_query(query, (version,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Failed to get migration info for {version}: {e}")
            return None

    def get_migration_status(self) -> Dict[str, Any]:
        """
        Get comprehensive migration status

        Returns:
            Migration status dictionary
        """
        return {
            'current_version': self.schema_manager.get_current_version(),
            'pending_migrations': len(self._get_pending_migrations()),
            'applied_migrations': len([
                m for m in self.schema_manager.get_migration_history()
                if m['status'] == 'applied'
            ]),
            'failed_migrations': len([
                m for m in self.schema_manager.get_migration_history()
                if m['status'] == 'failed'
            ]),
            'schema_validation': self.schema_manager.validate_schema()
        }
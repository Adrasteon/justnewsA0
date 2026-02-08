# Postgres-specific connection pool tests removed due to Postgres being deprecated.
import pytest

pytest.skip(
    "Postgres connection pool tests removed due to Postgres deprecation",
    allow_module_level=True,
)
# Tests that verify pool behavior for MariaDB / migrated service are covered
# in `migrated_database_utils` and other database-related tests.

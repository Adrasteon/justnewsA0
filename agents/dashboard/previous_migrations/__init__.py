# Database Migrations Package

"""
Database migration files for the JustNews database layer.

Migration files follow the naming convention: NNN_description.sql
where NNN is a zero-padded number indicating migration order.

Each migration file contains:
- UP section: SQL to apply the migration
- DOWN section: SQL to rollback the migration

Migrations are applied in order and can be rolled back individually
or to a specific point in the migration history.
"""

__version__ = "1.0.0"

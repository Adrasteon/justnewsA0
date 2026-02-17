# Applying Synthesis Migrations (004/005)

Use `scripts/ops/apply_synthesis_migration.sh`to safely apply the`004_add_synthesis_fields.sql` and
`005_create_synthesized_articles_table.sql` migrations in staging/production. The script logs output to
`logs/operations/migrations` and supports both MySQL/MariaDB and PostgreSQL connection strings.

Checklist:

1. Backup the database snapshot.

1. Run the script:

```bash

## Example for MariaDB

JUSTNEWS_DB_URL="mysql://user:pass@host:3306/justnews" scripts/ops/apply_synthesis_migration.sh

```

1. Verify `articles`table has new columns (Option A) or`synthesized_articles` table exists (Option B).

1. Run smoke tests: `justnews/tests/integration/test_article_creation_flow.py` (integration test) and check the
   dashboard health.

1. Record the migration evidence in `logs/operations/migrations`.

Rollbacks: use the down migration or manually drop the columns/tables after careful inspection.

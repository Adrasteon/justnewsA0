--- title: MariaDB integration description: 'Set the database URL in `/etc/justnews/global.env` (adjust
credentials/host):'

tags: ["adjust", "credentials", "database"] ---

# MariaDB integration

Set the database URL in `/etc/justnews/global.env` (adjust credentials/host):

```bash

JUSTNEWS_DB_URL=mysql://user:pass@localhost:3306/justnews

```

## Verification (on-host)

Use the helper to verify connectivity quickly:

```bash

sudo ./infrastructure/systemd/helpers/db-check.sh

```

If `mysql`is available, the script runs`SELECT 1`. Otherwise, it checks the Memory service health endpoint as a proxy.

See also: `infrastructure/systemd/QUICK_REFERENCE.md` for the minimal env examples.

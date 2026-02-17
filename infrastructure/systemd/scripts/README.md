check_db_services.sh — diagnostic helper ======================================

Purpose ------- Small, read-only helper that inspects systemd and connectivity for MariaDB and ChromaDB using the host's
`/etc/justnews/global.env` (or an alternative file passed via --env). Useful during deploy/startup troubleshooting when
`canonical_system_startup.sh` reports DB or Chroma connectivity failures.

Quick usage ----------- From the repository root:

```bash
sudo infrastructure/systemd/scripts/check_db_services.sh

```bash

Or point to a different environment file:

```bash
sudo infrastructure/systemd/scripts/check_db_services.sh --env /etc/justnews/global.env

```

What it checks --------------

- existence and enabled/active state of `mariadb`and`chromadb` systemd units

- last journal lines for each unit (helpful for immediate error patterns)

- MariaDB probe using `mysql` client or python+pymysql fallback

- Chroma probe via `curl /api/v2/auth/identity`(preferred) with fallbacks to`/api/v1/health`,`/api/v1/heartbeat`or`/` —
  or scripts/chroma_diagnose.py fallback

Notes -----

- The script is intentionally non-destructive and should be safe to run on
production or dev hosts.

- If you see failures, common fixes include:

- enable/start services: `sudo systemctl enable --now mariadb`and`sudo systemctl enable --now chromadb`

- re-run the setup helper `infrastructure/systemd/complete_mariadb.sh` to ensure DB users and schema are created

- double-check `/etc/justnews/global.env` for correct host/port/user/password

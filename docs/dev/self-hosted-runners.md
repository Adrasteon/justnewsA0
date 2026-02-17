# Self-hosted runner requirements for systemd-nspawn E2E

This repository includes a GitHub Actions job (.github/workflows/e2e-systemd- nspawn.yml) which performs a real E2E run
against MariaDB and Redis inside a systemd-nspawn container.

This job runs exclusively on self-hosted runners — it will not run on GitHub's hosted runners. The job expects the
runner to meet a number of system-level prerequisites.

Runner requirements

- A Linux host with systemd (Ubuntu or Debian recommended).

- A runner configured in GitHub self-hosted pool with labels: `self-hosted`,`linux`,`systemd` (the workflow uses these
  labels in runs-on).

- sudo or root access enabled for the runner so the workflow can run system-level commands (systemd-nspawn, machinectl,
  debootstrap). The workflow executes sturdy commands with `sudo`.

Packages / tooling required on the runner

- debootstrap

- systemd-container (provides systemd-nspawn and machinectl)

- rsync, tar, bc

Runner caching (optional but recommended)

- For faster CI runs, the workflow uses a prebuilt container cache at `/var/lib/ci_cache/justnews_test_base.tar.gz`on
  the runner. The repository ships`scripts/dev/setup_selfhosted_runner.sh` which can install required tooling and build
  a cache tarball. The workflow will reuse this cached container when present to avoid re-running debootstrap each job.

Security & safety notes

- The workflow uses system-level mechanisms and will create containers under /var/lib/machines. Ensure runners are
  dedicated for CI and isolated from other workloads.

- Avoid running this workflow on shared machines with developer data unless you trust the runner environment.

- The workflow uses sudo and will execute scripts as root on the runner; ensure proper runner access control along with
  GitHub runner-level policies.

Maintenance notes

- Keep runner images updated and with enough disk space to host the container image (debootstrap will download and
  install packages). Consider creating a prepared base image with a prebootstrapped container for faster runs.

- Add a cron or cleanup job on the runner to prune old containers under /var/lib/machines if you see disk pressure.

# Git hooks for JustNews (local developer helpers)

The repository includes a small set of optional git hooks that are intended as developer helpers. They are intentionally
non-mandatory and opt-in.

Why use them?

- Encourage test consistency by recommending the `scripts/dev/pytest.sh`wrapper that runs tests inside
  the project `.venv` environment.

- Optionally run a very quick unit smoke test on `pre-push` to catch obvious breakages before pushing to remote (non-
  default behavior).

Installation

From the repository root run:

```bash
./scripts/dev/install_hooks.sh

```

The installer copies scripts from `scripts/dev/git-hooks/`into`.git/hooks` and marks them executable.

Hook behavior

- `pre-push`: prints a recommendation to use the pytest wrapper. If you set`GIT_STRICT_TEST_HOOK=1`in your shell, the
  hook will also run a quick unit smoke test (`pytest -k "not integration" --maxfail=1`) and abort the push on failure.

FAQ

- Q: Are hooks enforced in CI? A: No — hooks are local, opt-in developer helpers and not enforced by CI. Server-side or
  branch protection policies are recommended for enforced checks.

- Q: How do I bypass the conda recommendation? A: Set `ALLOW_ANY_PYTEST_ENV=1` to bypass the local conftest check
  (useful for experimental runs or debugging).

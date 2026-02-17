import json
import re
from pathlib import Path

# Patterns we track (textual) and short suggestion messages
PATTERNS = {
    r"\bdatetime\.utcnow\(": "Use timezone-aware datetimes: datetime.now(timezone.utc)",
    r"asyncio\.get_event_loop\(\)\.run_until_complete": "Use asyncio.run() or async tests",
    r"\.run_until_complete\(": "Avoid run_until_complete; prefer asyncio.run or use async tests",
    r"\.dict\(\)": "Pydantic v2: prefer model_dump() instead of dict() where appropriate",
}

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "third_party",
    ".mypy_cache",
    "__pycache__",
    "tests/deprecation",
    "tests/codemod",
    "codemod",
    "deprecations",
    "codemods",
}


def _scan_repo():
    root = Path.cwd()
    results = {pat: [] for pat in PATTERNS}

    for p in root.rglob("*.py"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue

        try:
            text = p.read_text()
        except Exception:
            continue

        for pat in PATTERNS:
            regex = re.compile(pat)
            for i, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    results[pat].append(
                        {"path": str(p), "line": i, "content": line.strip()}
                    )

    return results


def _occurrence_key(o):
    return f"{o['path']}:{o['line']}"


def test_no_new_deprecations():
    baseline_path = Path("tests/deprecation/deprecations_baseline.json")
    assert baseline_path.exists(), (
        "Baseline file tests/deprecation/deprecations_baseline.json is missing. "
        "Run scripts/deprecations/find_deprecations.py --output=tests/deprecation/deprecations_baseline.json"
    )

    baseline = json.loads(baseline_path.read_text())
    found = _scan_repo()

    new_issues = {}
    for pat, matches in found.items():
        base_set = {f"{m['path']}:{m['line']}" for m in baseline.get(pat, [])}
        current_set = {f"{m['path']}:{m['line']}" for m in matches}

        # New occurrences are current_set - base_set
        new = sorted(current_set - base_set)
        if new:
            new_issues[pat] = {
                "suggestion": PATTERNS[pat],
                "new_occurrences": new,
            }

    if new_issues:
        msgs = []
        for pat, details in new_issues.items():
            msgs.append(
                f"Pattern: {pat}\nSuggestion: {details['suggestion']}\nNew occurrences:\n  "
                + "\n  ".join(details["new_occurrences"])
            )

        full = "\n\n".join(msgs)
        raise AssertionError(
            "New deprecation-like patterns were detected that are not in the baseline file.\n"
            "Please review and either fix the code, or if this is an allowed usage, add it to the baseline by running:\n"
            "  python scripts/deprecations/find_deprecations.py --output=tests/deprecation/deprecations_baseline.json\n\n"
            + full
        )

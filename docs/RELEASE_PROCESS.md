--- title: Release Process description: Auto-generated description for Release Process tags: [documentation] status:
current last_updated: 2025-10-18 ---

# Release Process

## Version Numbering

- **0.x.y**: Pre-release versions (development)

- **1.x.y**: Production releases

- **x.y.z**: Semantic versioning (MAJOR.MINOR.PATCH)

## Current Version: 0.8.0 (Beta Release Candidate)

## Release Checklist

### Pre-Release

- [ ] Run full test suite: `pytest`

- [ ] Update CHANGELOG.md with release notes

- [ ] Update version in `justnews/__init__.py`

- [ ] Update README.md version badges

- [ ] Validate version: `python scripts/check_version.py`

### Release Steps

1. **Create release branch:**

```
bash git checkout -b release/0.8.0
```

1. **Update version numbers:**

```bash
# Edit justnews/__init__.py
# Edit CHANGELOG.md
# Edit README.md

```bash

1. **Commit changes:**

```
bash git add . git commit -m "Release 0.8.0: Beta release candidate"
```

1. **Create annotated tag:**

```bash git tag -a v0.8.0 -m "Version 0.8.0 - Beta Release Candidate

Unified startup system with enterprise GPU orchestration

   - Complete systemd integration

   - MPS resource allocation

   - Production deployment capabilities

   - Comprehensive monitoring and recovery"

```

1. **Push to repository:**

```
bash git push origin release/0.8.0 git push origin v0.8.0
```

1. **Merge to main:**

```
bash git checkout main git merge release/0.8.0 git push origin main
```

### Post-Release

- [ ] Create GitHub release with release notes

- [ ] Update documentation links

- [ ] Notify stakeholders

- [ ] Monitor for issues

## Version Validation

Run version check:

```bash
python scripts/check_version.py

```

Expected output:

```

✅ JustNews Version: 0.8.0
📊 Status: beta
📅 Release Date: 2025-09-25
📝 Description: Beta release candidate with unified startup system and enterprise GPU orchestration

```

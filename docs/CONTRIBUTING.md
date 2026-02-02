--- title: 📚 JustNews V4 Documentation Contributor Guidelines description: Auto- generated description for 📚 JustNews V4
Documentation Contributor Guidelines tags: [documentation] status: current last_updated: 2025-09-12 ---

# 📚 JustNews V4 Documentation Contributor Guidelines

## 🎯 Overview

Welcome to the JustNews V4 documentation team! These guidelines ensure our documentation maintains the highest quality
standards and exceeds industry benchmarks. Our target is **>90% quality score** across all documentation.

**Current Status:** ✅ **100.0/100 Quality Score Achieved**

---

## 📋 Table of Contents

1. [Quality Standards](#quality-standards)

1. [Documentation Structure](#documentation-structure)

1. [Writing Guidelines](#writing-guidelines)

1. [Technical Requirements](#technical-requirements)

1. [Review Process](#review-process)

1. [Tools and Automation](#tools-and-automation)

1. [Version Control](#version-control)

---

## 🎯 Quality Standards

### Minimum Quality Thresholds

| Metric | Target | Current Status | |--------|--------|----------------| | **Overall Quality Score** | >90% | ✅
100.0/100 | | **Description Length** | 150+ characters | ✅ 201.5 avg | | **Tagging Coverage** | 100% | ✅ 100% | |
**Quality Issues** | 0 | ✅ 0 |

### Quality Score Components

1. **Description Score (50%)**: Based on average description length

- 200+ characters = 100 points

- 150-199 characters = 75 points

- 100-149 characters = 50 points

- <100 characters = 0 points

1. **Tagging Score (50%)**: Based on percentage of tagged documents

- 100% tagged = 100 points

- 90-99% tagged = 90 points

- <90% tagged = penalty applied

1. **Issue Penalty**: -5 points per quality issue

- Missing description (<50 chars)

- Missing tags

- Missing word count

---

## 📁 Documentation Structure

### Required Directory Structure

```bash

JustNews/
├── docs/
│   ├── docs_catalogue_v2.json    # 📋 Master catalogue
│   ├── quality_monitor.py        # 🔍 Quality monitoring
│   ├── version_control.py        # 📝 Version control
│   ├── CONTRIBUTING.md          # 📖 This file
│   └── quality_reports/         # 📊 Quality reports
├── markdown_docs/
│   ├── production_status/       # 🏭 Production updates
│   ├── agent_documentation/     # 🤖 Agent docs
│   ├── development_reports/     # 📈 Development reports
│   └── optimization_reports/    # ⚡ Performance reports
└── docs/                        # 📚 Technical docs

```

### Document Categories

1. **Main Documentation** (Critical Priority)

- README.md, CHANGELOG.md

- Installation and deployment guides

1. **Agent Documentation** (High Priority)

- Individual agent specifications

- API documentation and endpoints

1. **Technical Reports** (Medium Priority)

- Performance analysis

- Architecture documentation

- Development reports

1. **Maintenance Documentation** (Low Priority)

- Troubleshooting guides

- Backup and recovery procedures

---

## ✍️ Writing Guidelines

### Content Standards

#### 1. Descriptions

- **Minimum Length**: 150 characters

- **Target Length**: 200+ characters

- **Structure**: Problem → Solution → Benefits

- **Keywords**: Include relevant technical terms

**Example:**

```bash

❌ Poor: "Installation guide"
✅ Excellent: "Complete installation guide for JustNews V4 with RTX3090 GPU support, including dependency management, environment setup, and troubleshooting common issues."

```

#### 2. Titles

- **Clear and Descriptive**: Explain document purpose

- **Consistent Format**: Use title case

- **Include Key Terms**: GPU, AI, agents, etc.

#### 3. Tags

- **Required**: Every document must have tags

- **Relevant**: Use specific, searchable terms

- **Consistent**: Follow established tag conventions

**Tag Categories:**

- **Technical**: `gpu`,`tensorrt`,`api`,`database`

- **Functional**: `installation`,`deployment`,`monitoring`

- **Content**: `guide`,`report`,`documentation`,`tutorial`

### Style Guidelines

#### Language and Tone

- **Professional**: Use formal, technical language

- **Clear**: Avoid jargon without explanation

- **Concise**: Be comprehensive but not verbose

- **Active Voice**: Prefer active voice over passive

#### Formatting Standards

- **Markdown**: Use consistent Markdown formatting

- **Headers**: Use proper hierarchy (H1 → H2 → H3)

- **Code Blocks**: Use syntax highlighting

- **Lists**: Use bullet points for items, numbered lists for sequences

---

## 🔧 Technical Requirements

### Metadata Standards

Every document entry must include:

```json
{
  "id": "unique_identifier",
  "title": "Descriptive Title",
  "path": "relative/path/to/file.md",
  "description": "Comprehensive description (150+ chars)",
  "last_updated": "2025-09-07",
  "status": "production_ready|current|draft|deprecated",
  "tags": ["tag1", "tag2", "tag3"],
  "related_documents": ["doc_id1", "doc_id2"],
  "word_count": 1500
}

```bash

### File Standards

#### Naming Conventions

- **Lowercase**: Use lowercase with underscores

- **Descriptive**: Include key terms in filename

- **Extensions**: Use `.md` for Markdown files

**Examples:**

- ✅ `gpu_acceleration_guide.md`

- ✅ `agent_communication_protocol.md`

- ❌ `GPU_GUIDE.md`

- ❌ `doc1.md`

#### Version Control

- **Commits**: Use descriptive commit messages

- **Branches**: Create feature branches for changes

- **Pull Requests**: Required for all changes

---

## 🔍 Review Process

### Pre-Commit Checklist

Before committing changes:

- [ ] **Quality Check**: Run quality monitor

- [ ] **Validation**: Ensure all required fields present

- [ ] **Consistency**: Follow established patterns

- [ ] **Testing**: Verify changes don't break automation

- [ ] **Secrets & Sensitive Data**: DO NOT commit secrets (passwords, API keys, DSNs, private keys) to the repository.
  Use `global.env.sample`for non-secret placeholders and the Vault-based flow
  (`scripts/fetch_secrets_to_env.sh`→`/run/justnews/secrets.env`) for real secrets. Before committing, run a quick local
  scan, for example:

```bash git grep -nE "password|API_KEY|SENTRY_DSN|SECRET|PRIVATE_KEY|TOKEN" ||
true ```

If you accidentally commit secrets that were pushed to a remote, **rotate the
credentials immediately**, inform maintainers/security, and remove the sensitive
data from the repo history (contact core maintainers for assistance with `git
filter-repo`/remediation).

- [ ] **Markdown lint**: We run `markdownlint` in CI. To check locally in the canonical
  environment:

  ```bash
  # in canonical environment (defaults to ${CANONICAL_ENV:-justnews-py312-phase1})
  npm install -g markdownlint-cli
  markdownlint "**/*.md"
  ```

  The repository policy allows line lengths up to **200 characters** (MD013) and does
  not require a fence language for all fenced code blocks (MD040 disabled). If you
  need to override for a specific file, add a per-file `<!-- markdownlint-disable -->`
  comment or open a PR discussion.

### Automated Quality Checks

The system automatically validates:

1. **Description Length**: Minimum 150 characters

1. **Tag Coverage**: 100% of documents tagged

1. **Metadata Completeness**: All required fields present

1. **Format Consistency**: Proper JSON structure

### Manual Review Process

1. **Self-Review**: Author reviews their changes

1. **Peer Review**: Team member reviews changes

1. **Quality Validation**: Automated quality scoring

1. **Approval**: Changes approved and merged

---

## 🧪 Testing Guidelines

### Understanding the Phased Test System

JustNews uses a **phased testing architecture** with 4 isolated conda environments. Each phase runs **independently** to avoid dependency conflicts:

| Phase | Environment | Tests | GPU | Marker |
|-------|-------------|-------|-----|--------|
| 1 | `justnews-py312-phase1` | Ingestion, crawler, embeddings | ✅ | `@pytest.mark.phase1` |
| 2 | `justnews-py312-phase2` | Clustering, analytics, unit | ❌ | `@pytest.mark.phase2` |
| 3 | `justnews-py312-phase3` | Synthesis, LLM inference | ✅ | `@pytest.mark.phase3` |
| 4 | `justnews-py312-phase4` | Publishing, Django, web | ❌ | `@pytest.mark.phase4` |

### Running Tests Locally

**Before committing code that modifies tests or dependencies**, run the appropriate phase tests:

```bash
# Run tests for the phase you're developing in
./scripts/run_phase_tests.sh 1              # Phase 1 (GPU ingestion)
./scripts/run_phase_tests.sh 2              # Phase 2 (CPU clustering)
./scripts/run_phase_tests.sh 3              # Phase 3 (GPU synthesis)
./scripts/run_phase_tests.sh 4              # Phase 4 (CPU publishing)

# Run all phases sequentially
./scripts/run_phase_tests.sh all

# Or use Make targets
make test-phase1            # Single phase
make test-phased            # All phases
```

**Optional flags:**
```bash
./scripts/run_phase_tests.sh 1 --verbose    # Verbose output
./scripts/run_phase_tests.sh 1 --strict     # Stop on first failure (-x)
./scripts/run_phase_tests.sh 1 --collect-only  # Discover tests without running
```

### Writing Tests

When adding new tests:

1. **Identify the phase**: Which workflow phase does this test belong to?
2. **Add the marker**: Use `@pytest.mark.phase{1,2,3,4}` on your test
3. **No cross-phase imports**: Avoid importing from modules in other phases
4. **Test in the right environment**: Run `./scripts/run_phase_tests.sh {phase}` before committing

**Example test with phase marker:**
```python
import pytest

@pytest.mark.phase1
def test_ingestion_crawler():
    """Test phase 1 crawler functionality."""
    from agents.crawler import CrawlEngine
    # ... test code ...
```

### Pre-Commit Test Checklist

Before committing changes:

- [ ] **Type mapping**: Which phase does this change affect?
- [ ] **Test markers**: Are new tests tagged with correct phase marker?
- [ ] **Phase-specific tests pass**: 
  ```bash
  ./scripts/run_phase_tests.sh {phase} -x  # Stop on first failure
  ```
- [ ] **No new dependency conflicts**: Check `conda/environment.phase*.yml`
- [ ] **Documentation updated**: See [TESTING.md](TESTING.md) if adding new test categories

### CI Integration

The CI pipeline mirrors the phased approach:
- **Phase 1 Tests**: Run in CI with GPU resource pool
- **Phase 2 Tests**: Run in CI, CPU-only
- **Phase 3 Tests**: Run in CI with GPU resource pool  
- **Phase 4 Tests**: Run in CI, CPU-only

Your pull request must pass all phase tests relevant to your changes.

---

## 🛠️ Tools and Automation

### Quality Monitoring

```bash

## Run quality check

python docs/quality_monitor.py

## Continuous monitoring

python docs/quality_monitor.py --continuous --interval 24

```

### Version Control

```bash

## Create version snapshot

python docs/version_control.py snapshot --author "Your Name"

## Generate change report

python docs/version_control.py report --days 7

## View document history

python docs/version_control.py history --document "doc_id"

```bash

### Automated Scripts

#### Quality Enhancement

```python
from docs.quality_enhancement import QualityEnhancer

enhancer = QualityEnhancer() enhancer.analyze_quality_issues() enhancer.enhance_short_descriptions()

```

#### Catalogue Management

```python
from docs.automation_tools import DocumentationAutomation

automation = DocumentationAutomation() automation.generate_quality_dashboard() automation.validate_cross_references()

```

---

## 📝 Version Control Guidelines

### Commit Message Standards

```

type(scope): description

[optional body]

[optional footer]

```

**Types:**

- `feat`: New feature

- `fix`: Bug fix

- `docs`: Documentation changes

- `style`: Formatting changes

- `refactor`: Code refactoring

- `test`: Testing changes

- `chore`: Maintenance changes

**Examples:**

```

docs(catalogue): enhance GPU documentation descriptions

- Added detailed GPU acceleration guides

- Improved TensorRT integration documentation

- Updated performance metrics

Closes #123

```

### Branch Naming

```

feature/description-of-feature bugfix/issue-description docs/documentation-update hotfix/critical-fix

```

### Pull Request Process

1. **Create Branch**: From `main` or appropriate base

1. **Make Changes**: Follow quality guidelines

1. **Test Changes**: Run quality monitoring

1. **Create PR**: Descriptive title and body

1. **Code Review**: Address reviewer feedback

1. **Merge**: Squash merge with descriptive message

---

## 🚨 Quality Alerts

### Alert Thresholds

- **Critical**: <85% quality score

- **Warning**: 85-89% quality score

- **Good**: 90-94% quality score

- **Excellent**: 95-100% quality score

### Response Procedures

#### Critical Alert Response

1. **Immediate Action**: Stop all documentation work

1. **Root Cause Analysis**: Identify quality issues

1. **Fix Issues**: Address all critical problems

1. **Quality Verification**: Confirm score >90%

1. **Resume Normal Operations**

#### Warning Alert Response

1. **Monitor Closely**: Track quality trends

1. **Address Issues**: Fix identified problems

1. **Prevent Degradation**: Implement preventive measures

---

## 📊 Quality Metrics Dashboard

### Key Performance Indicators

1. **Quality Score Trend**: Track over time

1. **Issue Resolution Time**: Time to fix quality issues

1. **Documentation Coverage**: Percentage of features documented

1. **Update Frequency**: How often documentation is updated

### Reporting

- **Daily Reports**: Automated quality summaries

- **Weekly Reports**: Detailed analysis and trends

- **Monthly Reports**: Comprehensive quality assessment

- **Quarterly Reviews**: Strategic improvements

---

## 🎯 Best Practices

### Documentation Excellence

1. **Write for Multiple Audiences**

   - Technical experts

   - System administrators

   - Developers

   - End users

1. **Maintain Consistency**

   - Use consistent terminology

   - Follow established patterns

   - Maintain formatting standards

1. **Keep Documentation Current**

   - Update with code changes

   - Review regularly for accuracy

   - Archive outdated content

1. **Focus on User Experience**

   - Clear navigation and structure

   - Searchable and findable content

   - Practical examples and use cases

### Quality Maintenance

1. **Regular Audits**: Monthly quality reviews

1. **Automated Monitoring**: Continuous quality checks

1. **Team Training**: Regular guideline updates

1. **Feedback Integration**: User feedback incorporation

---

## 📞 Support and Resources

### Getting Help

- **Quality Issues**: Run quality monitor and review reports

- **Technical Questions**: Check existing documentation first

- **Process Questions**: Review this contributing guide

- **Tool Issues**: Check automation script documentation

### Resources

- **Quality Monitor**: `docs/quality_monitor.py`

- **Version Control**: `docs/version_control.py`

- **Automation Tools**: `docs/automation_tools.py`

- **Quality Reports**: `docs/quality_reports/`

---

## 📈 Continuous Improvement

### Quality Goals

**2025 Q4 Goals:**

- Maintain 95%+ quality score consistently

- Achieve 100% documentation coverage

- Implement advanced automation features

- Establish documentation metrics dashboard

### Innovation Areas

1. **AI-Powered Quality Enhancement**

1. **Automated Content Generation**

1. **Smart Tagging and Categorization**

1. **Real-time Quality Monitoring**

---

## ✅ Checklist for Contributors

### Before Starting Work

- [ ] Review current quality score

- [ ] Understand documentation structure

- [ ] Check existing similar documents

- [ ] Plan changes with quality impact in mind

### During Development

- [ ] Follow writing guidelines

- [ ] Include all required metadata

- [ ] Test changes with quality monitor

- [ ] Validate JSON structure

### Before Committing

- [ ] Run quality check

- [ ] Verify all fields complete

- [ ] Check formatting consistency

- [ ] Review change impact

### After Committing

- [ ] Monitor quality score

- [ ] Address any alerts promptly

- [ ] Update related documentation

- [ ] Share improvements with team

---

**Remember**: High-quality documentation is a critical component of JustNews
V4's success. Your contributions help maintain our industry-leading standards
and ensure the system remains accessible and maintainable.

**Thank you for contributing to JustNews V4 documentation! 🚀**

## See also

- Technical Architecture: markdown_docs/TECHNICAL_ARCHITECTURE.md

- Documentation Catalogue: docs/DOCUMENTATION_CATALOGUE.md

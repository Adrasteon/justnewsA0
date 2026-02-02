---
title: "JustNews V4.0.0"
description: "Production-ready multi-agent news analysis system with GPU-accelerated processing, continuous learning, and distributed architecture"
tags: ["justnews", "multi-agent", "ai", "news-analysis", "gpu"]
status: "current"
version: "4.0.0"
last_updated: "2026-02-02"
---

# JustNews V4.0.0

A production-ready multi-agent news analysis system featuring GPU-accelerated processing, continuous learning, and distributed architecture.

## 📚 Documentation

**All documentation is organized and indexed in the `docs/` directory.**

**👉 [START HERE: docs/INDEX.md](docs/INDEX.md)** ← Master navigation for all documentation

### Quick Links by Role

- **New Operators**: [Setup Guide](docs/operations/SETUP_GUIDE.md) → [Operator Quick Start](docs/operations/operator-quick-start.md)
- **DevOps/SysAdmins**: [Infrastructure Guide](infrastructure/README.md) → [Systemd Operations](infrastructure/systemd/README.md)
- **Developers**: [Developer Guide](docs/developer/README.md) → [API Reference](docs/api/README.md)
- **Troubleshooting**: [Troubleshooting Guide](docs/operations/TROUBLESHOOTING.md)

### Complete Documentation Index

All documentation is organized under `docs/`:
- **operations/** - Setup, configuration, troubleshooting, monitoring
- **infrastructure/systemd/** - Service orchestration and deployment
- **developer/** - Development guides and standards
- **api/** - REST API documentation
- **architecture_overview.md** - System design and patterns

## 🚀 Quick Start

### Prerequisites

- Python 3.12+ (via conda/mamba)
- MariaDB 10.11+
- Chrome/Chromium (for Crawl4AI)
- GPU with CUDA (recommended for local inference)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd JustNews
   ```

2. **Set up environment:**
   ```bash
   mamba env create -f environment.yml -n ${CANONICAL_ENV:-justnews-py312}
   conda activate ${CANONICAL_ENV:-justnews-py312}
   ```

3. **Initialize Database:**
   ```bash
   # Make sure your database credentials are set in .env
   python manage.py migrate
   ```

4. **Start the System:**
   See [docs/operations/STARTUP_CHECKLIST.md](docs/operations/STARTUP_CHECKLIST.md) for full startup instructions.

   ```bash
   sudo infrastructure/systemd/canonical_system_startup.sh
   ```

## 🏗️ System Architecture

JustNews employs a multi-agent architecture coordinated via the Model Context Protocol (MCP).

key components:
- **Agents**: located in `agents/` (Fact Checker, Crawler, Journalist, Editor, Publisher, etc.)
- **Shared Libraries**: located in `common/` and `agents/common/`
- **Infrastructure**: located in `infrastructure/` (Systemd services, configurations)

### Hardware & Inference Strategy
- **Primary Intelligence**: Qwen 2.5 14B Instruct (AWQ/Int4) served via vLLM.
- **Multi-modal Support**: Whisper (Audio) and Qwen-VL (Vision) loaded on-demand via a **Model Swapping** strategy to maximize VRAM availability for reasoning context.
- **Hardware Requirement**: Single NVIDIA GPU with 24GB VRAM (e.g., RTX 3090/4090) is required for the full pipeline.

## 🤝 Contributing

Please read [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for details on our code of conduct and the process for submitting pull requests.

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details.

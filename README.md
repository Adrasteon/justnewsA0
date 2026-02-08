# JustNews V4.0.0

A production-ready multi-agent news analysis system featuring GPU-accelerated processing, continuous learning, and distributed architecture.

## 📚 Documentation

**All detailed documentation has been moved to the `docs/` directory.**

- **Quick Start**: [docs/operations/STARTUP_CHECKLIST.md](docs/operations/STARTUP_CHECKLIST.md)
- **Architecture**: [docs/architecture_overview.md](docs/architecture_overview.md)
- **Workflow Orchestrator**: [docs/orchestrator/WORKFLOW_ORCHESTRATOR.md](docs/orchestrator/WORKFLOW_ORCHESTRATOR.md)
- **Developer Guide**: [docs/developer/README.md](docs/developer/README.md)
- **Diagnostic Tools**: [docs/tools/DIAGNOSTIC_SCRIPTS.md](docs/tools/DIAGNOSTIC_SCRIPTS.md)
- **API Reference**: [docs/api/README.md](docs/api/README.md)
- **Operations**: [docs/operations/README.md](docs/operations/README.md)

## 🚀 Quick Start

### Fastest Setup: VS Code Dev Container

For the quickest, most reliable development environment setup:

1. **Install** [VS Code](https://code.visualstudio.com/) and the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. **Open** the project in VS Code: `code .`
3. **Reopen** in container: Press `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"
4. **Wait** for initialization (~2-5 min) → Setup runs automatically:
   - Creates Python venv with UV package manager
   - Installs 100+ dependencies from `requirements-bootstrap.txt`
   - Waits for MariaDB, runs Django migrations
   - Verifies all services ready
5. **Done!** See [.devcontainer/README.md](.devcontainer/README.md) for details

### Prerequisites

- Python 3.12+ (via conda/mamba)
- MariaDB 10.11+
- Chrome/Chromium (for Crawl4AI)
- GPU with CUDA (recommended for local inference)

### Quick Start Commands (Manual Setup)

For Dev Container setup (fastest): See section above.

For **local manual setup**, see [docs/dev-setup.md](docs/dev-setup.md) for detailed options:

```bash
# Clone the repository
git clone <repository-url>
cd JustNews

# Option 1: Using UV (Recommended for speed)
pip install uv
uv venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -r requirements-bootstrap.txt

# Option 2: Using Conda/Mamba
mamba env create -f environment.yml -n justnews-py312
mamba activate justnews-py312

# Initialize database
source global.env  # Load configuration
python manage.py migrate

# Start the system
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
